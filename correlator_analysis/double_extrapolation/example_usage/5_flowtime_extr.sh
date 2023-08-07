#!/bin/bash

qcdtype=$1
corr=$2
basepath_work_data=$3
basepath_plot=$4
nproc=${5:-"20"}
if [ -z "$qcdtype" ] || [ -z "$corr" ] || [ -z "$basepath_work_data" ] || [ -z "$basepath_plot" ] ; then
    echo "Usage: $0 qcdtype corr basepath_work_data basepath_plot [nproc]"
    echo "choices for qcdtype: quenched_1.50Tc_zeuthenFlow hisq_ms5_zeuthenFlow"
    echo "choices for corr: EE BB EE_clover BB_clover"
    echo "Example: $0 hisq_ms5_zeuthenFlow EE ../../../../data/merged/ ../../../../plots/"
    exit
fi

(
    cd "$(dirname $0)" || exit

    if [ "$qcdtype" == quenched_1.50Tc_zeuthenFlow ]; then
        quenched_extr() {
            ../_5_flowtime_extr.py \
                --corr $corr \
                --qcdtype quenched_1.50Tc_zeuthenFlow \
                --custom_ylims $ylims \
                --finest_Nt 36 \
                --relflow_file "$basepath_work_data/$qcdtype/$corr/s144t36_b0754400/${corr}_s144t36_b0754400_relflows.txt" \
                --max_FlowradiusBytauT 0.3 \
                --min_FlowradiusBytauT 0.25 \
                --basepath $basepath_work_data --basepath_plot $basepath_plot \
                --use_tex --min_tauT_plot 0.25 \
                $Zf2file $noextr $output_suffix --nproc $nproc
        }

        Zf2file=""
        ylims="2.2 4"

        if [ "$corr" == "BB" ]; then
            ylims="2.5 3.8"
            noextr="--no_extr"
            output_suffix="--output_suffix _no_extr"
            quenched_extr
            Zf2file="--Zf2_file $basepath_work_data/$qcdtype/coupling/Z2_taufT2_nonpert.dat"
        fi
        output_suffix="--output_suffix _relflow"
        noextr=""

        quenched_extr

    elif [ "$qcdtype" == hisq_ms5_zeuthenFlow ]; then
        fine_Nts=(36 32 28 24)
        temps=(195 220 251 293)
        ylims=("3.9 10.5" "4 9" "4 8" "3.5 7.2")
        output_suffix="--output_suffix _relflow"
        # --flowtimes_finest /work/home/altenkort/work/correlators_flow/data/merged/hisq_ms5_zeuthenFlow/EE/s096t${fine_Nts[idx]}_b0824900_m002022_m01011/flowtimes_s096t${fine_Nts[idx]}_b0824900_m002022_m01011.dat \
        for idx in "${!temps[@]}"; do

            ../_5_flowtime_extr.py \
                --min_tauT_plot 0.249 --n_samples 10 \
                --corr $corr --qcdtype $qcdtype \
                --custom_ylims ${ylims[idx]} \
                --finest_Nt ${fine_Nts[idx]} \
                --combined_fit \
                --relflow_file "$basepath_work_data/$qcdtype/$corr/s096t${fine_Nts[idx]}_b0824900_m002022_m01011/${corr}_s096t${fine_Nts[idx]}_b0824900_m002022_m01011_relflows.txt" \
                --temp_subfolder T${temps[idx]} \
                --max_FlowradiusBytauT 0.3 \
                --min_FlowradiusBytauT 0.25 \
                --basepath $basepath_work_data --basepath_plot $basepath_plot \
                --use_tex \
                --slope_bounds -100 0 \
                --nproc $nproc $output_suffix
        done

    fi

    wait
)
