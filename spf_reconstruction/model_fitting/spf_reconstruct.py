#!/usr/bin/env python3

import lib_process_data as lpd
import numpy as np
import scipy.integrate
import scipy.optimize
import scipy.interpolate
from typing import NamedTuple
from latqcdtools.statistics import bootstr
import argparse
from spf_reconstruction.model_fitting.EE_UV_spf import get_spf, add_args
import numba

@numba.njit(cache=True)
def Gnorm(tauT: float):
    return np.pi ** 2 * (np.cos(np.pi * tauT) ** 2 / np.sin(np.pi * tauT) ** 4 + 1 / (3 * np.sin(np.pi * tauT) ** 2))


# ==============================================================

@numba.njit(cache=True)
def Kernel(OmegaByT: float, tauT: float):
    return np.cosh(OmegaByT / 2 - OmegaByT * tauT) / np.sinh(OmegaByT / 2)


@numba.njit(cache=True)
def En(n: int, OmegaByT: float, mu: str):
    x = np.log(1 + OmegaByT / np.pi)
    y = x / (1 + x)
    if mu == "alpha":
        return np.sin(np.pi * n * y)
    elif mu == "beta":
        return np.sin(np.pi * y) * np.sin(np.pi * n * y)


class SpfArgs(NamedTuple):
    model: str
    mu: str
    constrain: bool
    PhiuvByT3: scipy.interpolate.InterpolatedUnivariateSpline
    n_max: int
    OmegaByT_IR: float
    OmegaByT_UV: float
    p: float
    MinOmegaByT: float
    MaxOmegaByT: float
    prevent_overfitting: bool


@numba.njit(cache=True)
def PhiIR(OmegaByT: float, kappaByT3: float):
    return kappaByT3 / 2 * OmegaByT


# ========= Spf models =========
def SpfByT3(OmegaByT, spfargs, *fit_params):
    kappaByT3 = fit_params[0][0]
    if spfargs.model == "max":
        return np.maximum(kappaByT3 / 2 * OmegaByT, spfargs.PhiuvByT3(OmegaByT) * fit_params[0][1])
    elif spfargs.model == "smax":
        return np.sqrt((kappaByT3 / 2 * OmegaByT) ** 2 + (spfargs.PhiuvByT3(OmegaByT) * fit_params[0][1]) ** 2)
    elif spfargs.model == "sum":
        return (kappaByT3 / 2 * OmegaByT) + (spfargs.PhiuvByT3(OmegaByT) * fit_params[0][1])
    elif spfargs.model == "pnorm":
        return ((kappaByT3 / 2 * OmegaByT) ** spfargs.p + (spfargs.PhiuvByT3(OmegaByT) * fit_params[0][1]) ** spfargs.p)**(1/spfargs.p)
    elif spfargs.model == "line":
        x = OmegaByT
        y_IR = PhiIR(x, kappaByT3)
        y_UV = fit_params[0][1] * spfargs.PhiuvByT3(x)
        x2 = spfargs.OmegaByT_UV
        x1 = spfargs.OmegaByT_IR
        y2 = fit_params[0][1] * spfargs.PhiuvByT3(x2)
        y1 = PhiIR(spfargs.OmegaByT_IR, kappaByT3)
        slope = (y2-y1)/(x2-x1)
        intercept = (y1*x2-y2*x1) / (x2-x1)
        return y_IR*np.heaviside(x1-x, 1) + (slope*x+intercept)*np.heaviside(x-x1, 0)*np.heaviside(x2-x, 0) + y_UV*np.heaviside(x-x2, 0)
    elif spfargs.model == "plaw":
        x = OmegaByT
        y_IR = PhiIR(x, kappaByT3)
        y_UV = fit_params[0][1] * spfargs.PhiuvByT3(x)
        x2 = spfargs.OmegaByT_UV
        x1 = spfargs.OmegaByT_IR
        y2 = fit_params[0][1] * spfargs.PhiuvByT3(x2)
        y1 = PhiIR(spfargs.OmegaByT_IR, kappaByT3)
        exp = np.log(y1/y2)/np.log(x1/x2)
        prefactor = y1/x1**exp
        return y_IR*np.heaviside(x1-x, 1) + (prefactor*x**exp)*np.heaviside(x-x1, 0)*np.heaviside(x2-x, 0) + y_UV*np.heaviside(x-x2, 0)
    elif spfargs.model == "step":
        return PhiIR(OmegaByT, 2 * kappaByT3 * spfargs.PhiuvByT3(spfargs.OmegaByT_UV) / spfargs.OmegaByT_UV) * np.heaviside(spfargs.OmegaByT_UV - OmegaByT, 0) \
               + kappaByT3 * spfargs.PhiuvByT3(OmegaByT) * np.heaviside(OmegaByT - spfargs.OmegaByT_UV, 1)
    elif spfargs.model == "step_any":
        return PhiIR(OmegaByT, 2 * kappaByT3 * spfargs.PhiuvByT3(fit_params[0][1]) / fit_params[0][1]) * np.heaviside(fit_params[0][1] - OmegaByT, 0) \
               + kappaByT3 * spfargs.PhiuvByT3(OmegaByT) * np.heaviside(OmegaByT - fit_params[0][1], 1)
    elif spfargs.model == "fourier":
        if spfargs.constrain:
            coef_tmp = 1
            for i in range(1, spfargs.n_max + 1):
                coef_tmp += fit_params[0][i] * En(i, spfargs.MaxOmegaByT, spfargs.mu)
            c_nmax = (spfargs.PhiuvByT3(spfargs.MaxOmegaByT) / np.sqrt((0.5 * kappaByT3 * spfargs.MaxOmegaByT) ** 2 + (spfargs.PhiuvByT3(spfargs.MaxOmegaByT)) ** 2) - coef_tmp) / En(
                    spfargs.n_max + 1, spfargs.MaxOmegaByT, spfargs.mu)
        coef = 1
        for i in range(1, spfargs.n_max+1):
            coef += fit_params[0][i] * En(i, OmegaByT, spfargs.mu)

        if spfargs.constrain:
            coef += c_nmax * En(spfargs.n_max + 1, OmegaByT, spfargs.mu)

        if coef < 0:
            print("-", end="")
            return np.inf  # this results in infinite chisq whenever the spf becomes negative
        return np.sqrt((0.5 * kappaByT3 * OmegaByT) ** 2 + (spfargs.PhiuvByT3(OmegaByT)) ** 2) * coef
    elif spfargs.model == "trig":
        coef = 1
        for i in range(2, spfargs.n_max + 2):
            coef += fit_params[0][i] * En((i-1), OmegaByT, spfargs.mu)
        if coef < 0:
            print("-", end="")
            return np.inf  # this results in infinite chisq whenever the spf becomes negative
        return np.sqrt((kappaByT3/2 * OmegaByT) ** 2 + (fit_params[0][1] * spfargs.PhiuvByT3(OmegaByT)) ** 2) * coef
    else:
        print("Error: unknown spf model", spfargs.model)
        return np.nan


def Integrand(OmegaByT, tauT, spfargs, *fit_params):
    return 1. / np.pi * Kernel(OmegaByT, tauT) * SpfByT3(OmegaByT, spfargs, *fit_params)


def TargetCorr(tauT, spfargs, *fit_params):
    CorrTrial = []
    for i in range(len(tauT)):
        try:
            CorrTrial.append(scipy.integrate.quad(lambda OmegaByT: Integrand(OmegaByT, tauT[i], spfargs, *fit_params), spfargs.MinOmegaByT, spfargs.MaxOmegaByT)[0])
        except OverflowError as e:
            print(str(e) + " for integration appears at tauT=" + str(tauT[i]))
            return np.inf
    return CorrTrial


def chisq_dof(fit_params, xdata, ydata_sample, edata, spfargs, verbose=False):
    res = (ydata_sample - TargetCorr(xdata, spfargs, fit_params)) / edata
    chisqdof = np.sum(res ** 2) / (len(xdata) - len(fit_params))
    if verbose:
        print(['{0:.7f} '.format(i) for i in fit_params], '{0:.4f}'.format(chisqdof))

    threshold = 1
    if spfargs.prevent_overfitting and chisqdof < threshold:
        return threshold
    else:
        return chisqdof


def fit_single_sample_wrapper(index, ydata, fit_params_0, xdata, edata, spfargs, PhiUV, verbose):
    # wrapper for the true bootstrap
    ydata_sample = ydata[index]
    result = fit_single_sample(ydata_sample, fit_params_0, xdata, edata, spfargs, PhiUV, verbose)
    print(index, end=" ")
    return result


def fit_single_sample(ydata_sample, fit_params_0, xdata, edata, spfargs, OmegaByT_arr, verbose=False):

    if verbose:
        print("current correlator sample:", ydata_sample)

    fit_res = scipy.optimize.minimize(fun=chisq_dof, x0=fit_params_0, args=(xdata, ydata_sample, edata, spfargs, verbose), method='L-BFGS-B',
                                      options={'disp': 0, 'ftol': 1.0e-06}, bounds=[[0, np.inf], *[[None, None] for _ in range(len(fit_params_0)-1)]], callback=None)  # 'maxiter': MaxIter,   , *([[-1, 1]]*spfargs.n_max)])  # , 'xatol': args.tol, 'fatol': args.tol

    # now use the fit results for the parameters to compute the fitted spectral function and correlator

    # spectral function
    Spf = []
    for i in range(len(OmegaByT_arr)):
        Spf.append(SpfByT3(OmegaByT_arr[i], spfargs, fit_res.x))
    return_nan = False
    if any(n < 0 for n in Spf):
        print("negative spf for this sample. returning nan.")
        return_nan = True

    # correlator
    fit_corr = TargetCorr(xdata, spfargs, fit_res.x)
    for i in range(len(xdata)):
        fit_corr[i] /= Gnorm(xdata[i])

    # chisq
    chisqdof = chisq_dof(fit_res.x, xdata, ydata_sample, edata, spfargs, verbose)  # Note: this chisq_dof is appended to the end of Record!

    # stack the result into one long array, because the bootstrap is limited to 1D arrays. we'll need to accordingly extract this again later.
    result = np.hstack((fit_res.x, Spf, fit_corr, chisqdof))

    if return_nan:
        nans = np.empty(result.shape)
        nans[:] = np.nan
        return nans
    else:
        return result


def get_fileidentifier(args):

    def get_model_str(model, PhiUVtype, mu, constrainstr, nmax, p, OmegaByT_IR, OmegaByT_UV):
        if model == "fourier":
            model_str = model + "_" + PhiUVtype + "_" + constrainstr + "_" + str(mu) + "_" + str(nmax)
        elif model == "trig":
            model_str = model + "_" + PhiUVtype + "_" + "_" + str(mu) + "_" + str(nmax)
        elif model == "pnorm":
            model_str = str(model) + str(p) + "_" + PhiUVtype
        elif model == "line" or model == "plaw":
            model_str = str(model) + "_wIR" + str(OmegaByT_IR) + "_wUV" + str(OmegaByT_UV) + "_" + PhiUVtype
        else:
            model_str = str(model) + "_" + PhiUVtype
        return model_str

    constrainstr = "s1" if not args.constrain else "s2"  # s1 = dont constrain, s2 = constrain
    model_str = get_model_str(args.model, args.PhiUV_order, args.mu, constrainstr, args.nmax, args.p, args.OmegaByT_IR, args.OmegaByT_UV)

    # PhiUV identifiers
    if args.Nf is not None:
        model_str = model_str + "_Nf" + str(args.Nf)
    if args.T_in_GeV:
        model_str = model_str + "_T" + '{0:.3f}'.format(args.T_in_GeV)
    if args.omega_prefactor:
        model_str = model_str + "_min" + str(args.min_scale)
    if args.min_scale:
        model_str = model_str + "_w" + str(args.omega_prefactor)

    if args.add_suffix:
        args.add_suffix = "_" + args.add_suffix
    fileidentifier = model_str + "_" + str(args.nsamples) + "smpls_tauTgtr" + str(args.min_tauT) + args.add_suffix  # +'{:.0e}'.format(args.tol)  "_"+startstr

    return fileidentifier


def readin_corr_data(args):

    if args.mock_bootstrap:
        corr = np.loadtxt(args.input_corr)
        corr = corr[~np.isnan(corr).any(axis=1)]  # remove lines with NaN's
        corr = corr[corr[:, 0] >= args.min_tauT, :]  # filter out below min_tauT

        NtauT = len(corr)  # number of data points we can actually consider. this is NOT the actual nt.

        xdata = corr[:, 0]
        ydata_norm_mean = corr[:, 1]
        edata_of_ydata_norm_mean = corr[:, 2]

        # get rid of the pert. normalization in the data
        for i in range(NtauT):
            corr[:, 1:3] *= Gnorm(xdata[i])

        ydata = corr[:, 1]
        edata = corr[:, 2]

    else:
        ydata = np.load(args.input_corr)[:, :, 1]
        nt_half = ydata.shape[1]
        xdata = lpd.get_tauTs(int(nt_half * 2))

        mask = np.logical_and(~np.isnan(ydata[0]), xdata >= args.min_tauT)  # filter out NaN's and filter out below min_tauT

        xdata = xdata[mask]
        ydata = ydata[:, mask]

        NtauT = len(xdata)

        ydata_norm_mean = np.nanmedian(ydata, axis=0)
        edata_of_ydata_norm_mean = lpd.dev_by_dist(ydata, axis=0)
        for i in range(NtauT):
            ydata[:, i] *= Gnorm(xdata[i])
        edata = lpd.dev_by_dist(ydata, axis=0)

    return xdata, ydata, edata, ydata_norm_mean, edata_of_ydata_norm_mean


def load_PhiUV(args):
    OmegaByT_arr, g2, LO, NLO = get_spf(args.Nf, args.max_type, args.min_scale, args.T_in_GeV, args.omega_prefactor, args.Npoints, args.Nloop)
    if args.PhiUV_order == "LO":
        PhiUVByT3 = LO
    elif args.PhiUV_order == "NLO":
        PhiUVByT3 = NLO
    else:
        print("ERROR: unknown --PhiUV_order")
        exit(1)
    # interpolate the UV spf for the integration. spline order: 1 linear, 2 quadratic, 3 cubic ...
    order = 3
    PhiUVByT3_interpolation = scipy.interpolate.InterpolatedUnivariateSpline(OmegaByT_arr, PhiUVByT3, k=order, ext=2)
    MinOmegaByT = OmegaByT_arr[0]
    MaxOmegaByT = OmegaByT_arr[-1]

    return OmegaByT_arr, PhiUVByT3_interpolation, PhiUVByT3, MinOmegaByT, MaxOmegaByT


def get_initial_guess(args):
    # set up initial guess for the fitted parameters.
    # for model 2, the initial guess for kappa is 1, and for the c_n is 0.
    # for other models we only have one other fit parameter which is the overall coefficient for the UV part, whose initial guess is 1.
    if args.model == "fourier":
        fit_params_0 = [1.]
        if args.constrain:
            args.nmax -= 1
        for i in range(args.nmax):
            fit_params_0.append(0.)
    elif args.model == "trig":
        fit_params_0 = [1., 1.]
        for i in range(args.nmax):
            fit_params_0.append(0.)
    elif args.model == "step":
        fit_params_0 = [1, ]
    else:
        fit_params_0 = [1, 1]
    print("Initial guess for fit params:", fit_params_0)
    return fit_params_0


def save_results(args, results, error, samples, xdata, ydata_norm_mean, edata_of_ydata_norm_mean, OmegaByT_arr, PhiUVByT3, nparam):
    NtauT = len(xdata)
    # make handling of the left and right 68-quantiles easier
    error = np.asarray(error)
    error = np.swapaxes(error, 0, 1)
    print(error.shape)

    nomega = len(OmegaByT_arr)
    structure = np.asarray((
        (0, nparam),
        (nparam, nparam+nomega),
        (nparam+nomega, nparam+nomega+NtauT),
        (nparam+nomega+NtauT, nparam+nomega+NtauT+1)
    ), dtype=int)

    fileidentifier = get_fileidentifier(args)
    outputfolder = args.output_path + "/" + fileidentifier + "/"
    lpd.create_folder(outputfolder)
    print("saving results into", outputfolder)

    np.savetxt(outputfolder + "samples_structure.dat", structure, header='This file contains pairs (a,b) of indices with which to split the array '
                                                                         'in the samples.npy in the correct way. Example: Spf=samples(a:b). \n rows for (a,b) in order: fit_resx, Spf, '
                                                                         'fit_corr, chisqdof', fmt='%i')
    np.save(outputfolder + "samples", samples)

    # extract the various quantities that have been stacked together due to bootstrap being limited to 1D arrays
    fit_resx = results[structure[0, 0]:structure[0, 1]]
    fit_resx_err = error[structure[0, 0]:structure[0, 1]]
    Spf = results[structure[1, 0]:structure[1, 1]]
    Spf_err = error[structure[1, 0]:structure[1, 1]]
    fit_corr = results[structure[2, 0]:structure[2, 1]]
    fit_corr_err = error[structure[2, 0]:structure[2, 1]]
    chisqdof = results[structure[3, 0]]
    chisqdof_err = error[structure[3, 0]]

    # combine fit params and chisqdof into one object for file storage
    fit_resx_data = np.column_stack((fit_resx, fit_resx_err))
    chisqdof_data = np.asarray(((chisqdof, *chisqdof_err),))
    fitparams_chisqdof = np.concatenate((fit_resx_data, chisqdof_data), axis=0)

    print("\nThe first line contains kappa/T^3. The last line contains chisq/dof. In between are c_i.\n"
          "param                  error_left    error_right:")
    print(fitparams_chisqdof)

    # save the Phi UV
    data = np.column_stack((OmegaByT_arr, PhiUVByT3))
    np.save(outputfolder + "/phiUV.npy", data)  # format: omegaByT, PhiUVByT3

    # save reconstructed fit spf
    data = np.column_stack((OmegaByT_arr, Spf, Spf_err))
    np.save(outputfolder + "/spffit.npy", data)  # format omegaByT, SpfByT3, err-, err+

    # save fitparams and chisqdof
    np.savetxt(outputfolder + "/params.dat", fitparams_chisqdof, fmt='%22.15e',
               header="The first line contains kappa/T^3. The last line contains chisq/dof. In between are c_i.\n"
                      "param                  error_left                 error_right:")

    # save reconstructed correlator
    np.savetxt(outputfolder + "/corrfit.dat",
               np.column_stack((xdata, ydata_norm_mean, edata_of_ydata_norm_mean, fit_corr, fit_corr_err)),
               fmt='%16.15e', header='tauT                corr(orig)            err(orig)             corr(fit)             err(-/+)')


def parse_args():
    parser = argparse.ArgumentParser()
    requiredNamed = parser.add_argument_group('required named arguments')

    # file names
    parser.add_argument('--output_path', help='the path of output folder like /a/b', type=str, required=True)
    parser.add_argument('--add_suffix', help='add an extra suffix to the output files in order to not overwrite previous ones with similar parameters on a '
                                             'different data set', type=str, default="")

    # input corr
    # TODO add support for multiple input_corrs
    parser.add_argument('--input_corr', help='Path to input correlator data file. expects text file with three columns: tauT, G, err', type=str)
    parser.add_argument('--min_tauT', help='ignore corr data below this tauT', type=float, default=0)
    parser.add_argument('--mock_bootstrap', help="if input_corr already contains mean and error values instead of bootstrap samples, "
                                                 "then do a mock bootstrap instead of a real one.", default=False, action="store_true")

    # === spf model selection ===
    requiredNamed.add_argument('--model', help='which model to use', choices=["max", "smax", "line", "step_any", "pnorm", "plaw", "sum", "fourier", "trig"], type=str,
                               required=True)
    requiredNamed.add_argument('--PhiUV_order', help='specify it this is LO or NLO.', type=str,
                               choices=["LO", "NLO"])

    # parameters for fourier model
    parser.add_argument('--mu', help='which "en" function to use', choices=["alpha", "beta"], type=str)
    parser.add_argument('--nmax', help='what nmax to use. valid only for model 1,2.', type=int, choices=[1, 2, 3, 4, 5, 6, 7])
    parser.add_argument('--constrain', help='force the spf to reach the UV limit at large omega', action="store_true")  # TODO remove

    # parameters for line,plaw model
    parser.add_argument('--OmegaByT_IR', type=float, help="three reasonable choices: 0.01, 0.4, 1")
    parser.add_argument('--OmegaByT_UV', type=float, default=2.2, help="default value: vacuum NLO and HTL-resummed NLO agree down to omega/T=2.2")

    # parameters for pnorm
    parser.add_argument('--p', type=float, help="parameter for pnorm model. p=2 is identical to smax. p=inf is identical to max.")

    # miscellaneous
    parser.add_argument('--prevent_overfitting', help="stops the minimum search of the fit as soon as chisq/dof < 1.", action="store_true")
    parser.add_argument('--nsamples', help='number of bootstrap samples to draw/consider.', type=int, default=None)
    parser.add_argument('--nproc', help='number of processes for the parallel bootstrap', default=1, type=int)
    parser.add_argument('--verbose', help='output current fit parameters at each iteration', action="store_true")
    parser.add_argument('--seed', help='seed for gaussian bootstrap sample drawings', default=0, type=int)

    PhiUV_parser = parser.add_argument_group('arguments for PhiUV')
    add_args(PhiUV_parser)

    # global args
    args = parser.parse_args()

    # check for missing params
    if (args.model == "fourier" or args.model == "trig") and (not args.mu or not args.nmax):
        print("ERROR: Need mu and nmax for model=fourier.")
        exit(1)
    if (args.model == "line" or args.model == "plaw") and not args.OmegaByT_UV:
        print("ERROR: Need OmegaByT_UV for model line or plaw.")
        exit(1)

    return args


def main():

    args = parse_args()

    OmegaByT_arr, PhiUVByT3_interpolation, PhiUVByT3, MinOmegaByT, MaxOmegaByT = load_PhiUV(args)
    xdata, ydata, edata, ydata_norm_mean, edata_of_ydata_norm_mean = readin_corr_data(args)

    fit_params_0 = get_initial_guess(args)
    nparam = len(fit_params_0)

    # constant parameters only used by the function SpfByT3
    spfargs = SpfArgs(args.model, args.mu, args.constrain, PhiUVByT3_interpolation, args.nmax, args.OmegaByT_IR, args.OmegaByT_UV, args.p, MinOmegaByT, MaxOmegaByT, args.prevent_overfitting)

    if args.mock_bootstrap:
        samples, results_mean, results_mean_err = \
            bootstr.bootstr_from_gauss(fit_single_sample, ydata, edata, args.nsamples, sample_size=1, return_sample=True, seed=args.seed, err_by_dist=True,
                                       useCovariance=False, parallelize=True, nproc=args.nproc, asym_err=True,
                                       args=(fit_params_0, xdata, edata, spfargs, OmegaByT_arr, args.verbose))
    else:
        if args.nsamples is None:
            args.nsamples = len(ydata)
        else:
            print("WARN: only using", args.nsamples, "of", len(ydata), "samples.")
        results = lpd.parallel_function_eval(fit_single_sample_wrapper, range(0, args.nsamples), args.nproc, ydata, fit_params_0, xdata, edata, spfargs, OmegaByT_arr, args.verbose)
        results = np.asarray(results)
        results_mean = np.median(results, axis=0)
        results_mean_err = lpd.dev_by_dist(results, axis=0, return_both_q=True)
        samples = ydata

    save_results(args, results_mean, results_mean_err, samples, xdata, ydata_norm_mean, edata_of_ydata_norm_mean, OmegaByT_arr, PhiUVByT3, nparam)


if __name__ == '__main__':
    lpd.print_script_call()
    main()
    lpd.save_script_call()

    # TODO multi-corr fits. something like this:
    # for corr, T_in_GeV in zip(args.corr, args.T_in_GeV):
        # bootstrap can handle nd arrays -> make corr a 3d array. PhiUV becomes an array as well.
        # think about organizing fitparameters differently.
        # in chisq calculation, add together chisq's for each corr by looping over corrs.
        # results become one more dimension.
        # save results for each corr. indicate whether a combined fit was done.