#!/usr/local/bin/python3.7m -u

import lib_process_data as lpd
import numpy
import scipy.integrate
import scipy.interpolate
import argparse
import itertools


def Gnorm(tauT):
    norm = numpy.pi ** 2 * (numpy.cos(numpy.pi * tauT) ** 2 / numpy.sin(numpy.pi * tauT) ** 4 + 1 / (3 * numpy.sin(numpy.pi * tauT) ** 2))
    return norm


# ====================


def model3(OmegaByT, kappa, PhiuvByT3, UV_prefactor):
    return numpy.maximum(PhiIR(OmegaByT, kappa), UV_prefactor * PhiuvByT3(OmegaByT))


def UV_part(OmegaByT, PhiuvByT3, UV_prefactor):
    return UV_prefactor * PhiuvByT3(OmegaByT)


def PhiIR(OmegaByT, kappa):
    return kappa * OmegaByT / 2


def Kernel(OmegaByT, tauT):
    return numpy.cosh(OmegaByT / 2 - OmegaByT * tauT) / numpy.sinh(OmegaByT / 2)


def Integrand(OmegaByT, tauT, spf, *args):
    return 1. / numpy.pi * Kernel(OmegaByT, tauT) * spf(OmegaByT, *args)


# find frankenstein continuum correlator at various fixed flowradiusBytauT
def find_and_plot_and_save_frankenstein(flowradiusBytauT_list, possible_tauTs, y_int_list, e_int_list, out_file_path, ax, color_list, Glabel):
    # find frankenstein continuum correlator at various fixed flowradiusBytauT
    frankenstein_arr = []
    for f, flowradiusBytauT in enumerate(flowradiusBytauT_list):
        frankenstein_edata = []
        frankenstein_ydata = []
        frankenstein_xdata = []
        for i, tauT in enumerate(possible_tauTs):
            wanted_flowradius = flowradiusBytauT * tauT
            if y_int_list[i] is not None:
                try:
                    frankenstein_edata.append(e_int_list[i](wanted_flowradius))
                    frankenstein_ydata.append(y_int_list[i](wanted_flowradius))
                    frankenstein_xdata.append(tauT)
                except ValueError:
                    pass
        frankenstein_arr.append(numpy.column_stack((frankenstein_xdata, frankenstein_ydata, frankenstein_edata)))
        numpy.savetxt(out_file_path+"frankenstein_"+r'{0:.3f}'.format(flowradiusBytauT)+".txt",
                      numpy.column_stack((frankenstein_xdata, frankenstein_ydata, frankenstein_edata)),
                      header="tauT      G/Gnorm_sqrt(8tauF)/tau="+r'{0:.3f}'.format(flowradiusBytauT)+"       err")
        ax.errorbar(frankenstein_xdata, frankenstein_ydata, frankenstein_edata, zorder=-len(flowradiusBytauT_list)+f,
                    **lpd.chmap(lpd.plotstyle_add_point, markersize=0, elinewidth=0.5, mew=0.5, fmt='x', color=color_list[f],
                                label=r'$G_\mathrm{' + Glabel + r'}^{\sqrt{8\tau_\text{F}}/\tau='+r'{0:.3f}'.format(flowradiusBytauT)+r'}$'))  #


def main():
    parser = argparse.ArgumentParser()

    # TODO: generalize all the hardcoded paths, especially the output folder and output plot name!

    parser.add_argument('--fitparam_files', nargs='*', help='plot model 3 spf for these fit params', required=True)
    parser.add_argument('--use_tex', action="store_true")
    parser.add_argument('--npoints', help='how many tauT to plot between 0 and 0.5 for the model correlators', default=100, type=int)
    parser.add_argument('--ylims', help='custom ylims', nargs=2, type=float, default=(-0.03, 4))
    parser.add_argument('--xlims', help='custom xlims', nargs=2, type=float, default=(-0.01, 0.51))
    parser.add_argument('--flowradiusBytauT', nargs='*', type=float, help='which sqrt(8tauF)/tauT to plot', required=True)
    parser.add_argument('--PhiUV_files', type=str, nargs='*', help='path to PhiUV file. expects three columns: omega/T, PhiUVByT3, err', required=True)
    parser.add_argument('--plot_quenched_extr', help='whether to plot the 1.5 Tc quenched continuum/flow-extr EE data', action="store_true")  # TODO soften hard code
    parser.add_argument('--title', help='title of plot', default=r'quenched, $1.5 T_c$, IR=$\kappa \omega /2T$', type=str)

    # when you want to load finite lattice spacing
    parser.add_argument('--qcdtype', help="list of qcdtypes. format doesnt matter, only used for finding data. example: quenched_1.50Tc_zeuthenFlow", nargs='*', type=str)
    parser.add_argument('--corr', help="list of corrs. choose from EE, EE_clover, BB, BB_clover", nargs='*', type=str)
    parser.add_argument('--conftype', nargs='*', type=str, help="list of conftypes, e.g. s080t20_b0703500 s096t24_b0719200 s120t30_b0739400 s144t36_b0754400")
    parser.add_argument('--min_tauT', default=0.2, type=float, help='lower limit from which tauT on the reconstructed corr is valid/should be plotted. can be '
                                                                    'overwritten by larger tauT parsed from fitparam file.')

    args = parser.parse_args()

    # calc reconstructed corrs for all given fitparam and PhiUV files.
    xpoints_arr = []
    model3_means = []
    model3_uppers = []
    model3_lowers = []
    fitparams = []
    just_UVs = []
    for fitparam_file, PhiUV_file in zip(args.fitparam_files, args.PhiUV_files):
        # load PhiUV
        PhiUVa = numpy.loadtxt(PhiUV_file, unpack=True)[0:3]
        PhiUVaByT3 = scipy.interpolate.InterpolatedUnivariateSpline(PhiUVa[0], PhiUVa[1], k=3)
        MinOmegaByT = 0
        MaxOmegaByT = PhiUVa[0][-1]

        # find out lower tauT based on file path
        tmp = lpd.remove_left_of_last('/', fitparam_file)
        tmp = lpd.remove_right_of_last('.dat', tmp)
        tmp = "0"+lpd.remove_left_of_first('_0', tmp)
        this_mintauT = float(lpd.remove_right_of_first('_', tmp))
        this_mintauT = numpy.fmax(args.min_tauT, this_mintauT)
        xpoints_arr.append(numpy.linspace(this_mintauT, 0.5, args.npoints))
        params, err_left, err_right = numpy.loadtxt(fitparam_file, unpack=True)
        fitparams.append(numpy.column_stack((params, err_left, err_right)))
        model3_mean = []
        model3_lower = []
        model3_upper = []
        just_UV = []
        for flowindex in xpoints_arr[-1]:
            model3_mean.append(scipy.integrate.quad(
                lambda OmegaByT: Integrand(OmegaByT, flowindex, model3, params[0], PhiUVaByT3, params[1]), MinOmegaByT, MaxOmegaByT)[0] / Gnorm(flowindex))
            model3_lower.append(scipy.integrate.quad(
                lambda OmegaByT: Integrand(OmegaByT, flowindex, model3, params[0]-err_left[0], PhiUVaByT3, params[1]-err_left[1]), MinOmegaByT, MaxOmegaByT)[0] / Gnorm(flowindex))
            model3_upper.append(scipy.integrate.quad(
                lambda OmegaByT: Integrand(OmegaByT, flowindex, model3, params[0]+err_right[0], PhiUVaByT3, params[1]+err_right[1]), MinOmegaByT, MaxOmegaByT)[0] / Gnorm(flowindex))
            just_UV.append(scipy.integrate.quad(
                lambda OmegaByT: Integrand(OmegaByT, flowindex, UV_part, PhiUVaByT3, params[1]), MinOmegaByT,
                MaxOmegaByT)[0] / Gnorm(flowindex))
        model3_means.append(model3_mean)
        model3_lowers.append(model3_lower)
        model3_uppers.append(model3_upper)
        just_UVs.append(just_UV)

    # prepare plot canvas
    fig, ax, _ = lpd.create_figure(xlims=args.xlims, ylims=args.ylims, xlabel=r'$\tau T$', xlabelpos=(0.95, 0.05), ylabelpos=(0.08, 0.9),
                                   UseTex=args.use_tex,
                                   ylabel=r'$\frac{G}{ G^\mathrm{norm} }$', figsize=(1.5 * (3 + 3 / 8), 1.5 * (3 + 3 / 8) / 16 * 9))

    colors = ('k', 'C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9')

    color_offset = 0
    if args.plot_quenched_extr:
        color_offset = 1
        # plot cont+flow extr. corr
        # TODO abstract this or make a flag to plot this or not?
        XX_flow_extr = numpy.loadtxt("/work/home/altenkort/work/correlators_flow/data/merged/quenched_1.50Tc_zeuthenFlow/EE/EE_flow_extr.txt", unpack=True)
        ax.errorbar(XX_flow_extr[0], XX_flow_extr[1], XX_flow_extr[2], zorder=0, **lpd.chmap(lpd.plotstyle_add_point, color='k', fmt='x', markersize=0, mew=0.5, elinewidth=0.5,
                                                                                             label=r'$G^{\tau_\text{F}\rightarrow 0}_\mathrm{cont}$'))

        # load continuum quenched data and interpolate it
        EE_cont_arr = []
        flowradii = numpy.loadtxt("/work/home/altenkort/work/correlators_flow/data/merged/quenched_1.50Tc_zeuthenFlow/EE/s144t36_b0754400/flowradii_s144t36_b0754400.dat")
        min_idx = 0
        max_idx = 0
        stop = False
        for flowradius in flowradii:
            flowradius_str = r'{0:.4f}'.format(flowradius)
            fitparam_file = "/work/home/altenkort/work/correlators_flow/data/merged/quenched_1.50Tc_zeuthenFlow/EE/cont_extr/EE_" + flowradius_str + "_cont.txt"
            try:
                EE_cont_arr.append(numpy.loadtxt(fitparam_file, unpack=True))
                stop = True
                max_idx += 1
            except OSError:
                # print("could not find ", file)
                if not stop:
                    min_idx += 1
        max_idx += min_idx
        flowradii = flowradii[min_idx:max_idx]  # filter which flowradii got actually read in
        possible_tauTs = EE_cont_arr[0][0]  # doesn't matter which one we choose here, they are all the same

        # interpolate between flowtimes for each tauT. for that we first need to remove the nan's
        cont_int = []
        cont_err_int = []
        for i in range(len(possible_tauTs)):
            ydata = numpy.asarray([EE_cont[1][i] for EE_cont in EE_cont_arr])
            edata = numpy.asarray([EE_cont[2][i] for EE_cont in EE_cont_arr])
            mask = ~numpy.isnan(ydata)
            xdata = flowradii[mask]
            ydata = ydata[mask]
            edata = edata[mask]
            if len(xdata) >= 3:
                cont_int.append(scipy.interpolate.InterpolatedUnivariateSpline(xdata, ydata, k=3, ext=2, check_finite=True))
                cont_err_int.append(scipy.interpolate.InterpolatedUnivariateSpline(xdata, edata, k=3, ext=2, check_finite=True))
            else:
                cont_int.append(None)
                cont_err_int.append(None)
        find_and_plot_and_save_frankenstein(args.flowradiusBytauT, possible_tauTs, cont_int, cont_err_int,
                                            "/work/home/altenkort/work/correlators_flow/data/merged/quenched_1.50Tc_zeuthenFlow/EE/", ax, colors, r'cont')

    # find frankenstein correlator at various fixed flowradiusBytauT
    if args.qcdtype is not None and args.corr is not None and args.conftype is not None:
        for qcdtype, corr, conftype, color in itertools.zip_longest(args.qcdtype, args.corr, args.conftype, colors[color_offset:color_offset+len(args.conftype)]):
            if qcdtype is None:
                qcdtype = args.qcdtype[0]
            if corr is None:
                corr = args.corr[0]
            inputfolder = lpd.get_merged_data_path(qcdtype, corr, conftype)
            these_flowradii = numpy.loadtxt(inputfolder + "flowradii_" + conftype + ".dat")
            XX = numpy.loadtxt(inputfolder + corr + "_" + conftype + ".dat")
            XX_err = numpy.loadtxt(inputfolder + corr + "_err_" + conftype + ".dat")
            beta, ns, nt, nt_half = lpd.parse_conftype(conftype)
            these_tauT = numpy.arange(1/nt, 0.501, 1/nt)

            # interpolate between flow times
            y_int = []
            e_int = []
            for i in range(len(these_tauT)):
                ydata = numpy.asarray(XX[:, i] * lpd.improve_corr_factor(i, nt))
                edata = numpy.asarray(XX_err[:, i] * lpd.improve_corr_factor(i, nt))
                xdata = these_flowradii
                y_int.append(scipy.interpolate.InterpolatedUnivariateSpline(xdata, ydata, k=3, ext=2, check_finite=True))
                e_int.append(scipy.interpolate.InterpolatedUnivariateSpline(xdata, edata, k=3, ext=2, check_finite=True))

            find_and_plot_and_save_frankenstein(args.flowradiusBytauT, these_tauT, y_int, e_int,
                                                inputfolder, ax, (color,), r'N_\tau='+str(nt))

    # plot reconstructed correlators with "error bands"
    for xpoints, model3_mean, model3_upper, model3_lower, just_UV, fitparam, color, zorder in zip(xpoints_arr, model3_means, model3_uppers, model3_lowers, just_UVs, fitparams, colors, range(len(xpoints_arr))):
        # ax.fill_between(xpoints, model3_lower, model3_upper, linewidth=0,  color=color, alpha=0.3, zorder=-zorder-1000)
        ax.errorbar(xpoints, model3_mean, color=color, alpha=1,
                    label="$ G_\\mathrm{fit}^{\\rho =\\mathrm{max(IR,c\\,UV_{a})}}$ \n "
                          "$ \\kappa/T^3=" + "{0:.3f}".format(fitparam[0][0])
                          + "\\pm " + "{0:.3f}".format(numpy.fmax(fitparam[0][1], fitparam[0][2]))
                          + "$\n $ c=" + "{0:.3f}".format(fitparam[1][0]) + "\\pm " + "{0:.3f}".format(numpy.fmax(fitparam[1][1], fitparam[1][2])) + "$ \n"
                          + "$\\chi^2/\\mathrm{dof}=" + "{0:.1f}".format(fitparam[2][0]) + " \\pm " + "{0:.1f}".format(numpy.fmax(fitparam[2][1], fitparam[2][2])) +"$",
                    **lpd.chmap(lpd.plotstyle_add_point, fmt='--', zorder=-zorder-100,))
        ax.errorbar(xpoints, just_UV, color=color, alpha=0.25,
                    **lpd.chmap(lpd.plotstyle_add_point, lw=0.4, fmt='-.', zorder=-zorder-10000,))

    lpd.legendstyle.update(dict(loc="lower right", bbox_to_anchor=(1.01, 0.07), labelspacing=2))
    ax.legend(title=r'$G=$', **lpd.chmap(lpd.legendstyle, bbox_to_anchor=(1, 0.5), loc='center left', ncol=1, fontsize=4))
    ax.set_title(args.title, x=0.5, y=1, fontsize=8)

    fig.savefig("/work/home/altenkort/work/correlators_flow/plots/quenched_1.50Tc_zeuthenFlow/EE/EE_frankenstein_comparison.pdf")


if __name__ == '__main__':
    lpd.print_script_call()
    main()
    lpd.save_script_call()
