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

if [ "$qcdtype" == quenched_1.50Tc_zeuthenFlow ] ; then
    arr_conftypes=("s080t20_b0703500" "s096t24_b0719200" "s120t30_b0739400" "s144t36_b0754400")
        min_trajs=(
        "0 0 0 0 0 0 0 0 0 0"
        "0 0 0 0 0 0 0 0 0 0"
        "0 0 0 0 0 0 0 0 0 0"
        "0 0 0 0 0 0 0 0 0 0"
    )
    MC_stepsize=500
    add_args=" --already_equally_spaced --show_id 0 1 --skip_binning --update_str sweeps"
elif  [ "$qcdtype" == hisq_ms5_zeuthenFlow ] ; then
    add_args="--n_samples 10"
    arr_conftypes=(
    "s064t20_b0803600" "s064t22_b0814700" "s096t24_b0824900_m002022_m01011"
    "s064t20_b0785700" "s064t24_b0806800" "s096t28_b0824900_m002022_m01011"
    "s064t20_b0770400" "s064t24_b0791300" "s096t32_b0824900_m002022_m01011"
    "s064t20_b0757000" "s064t24_b0777700" "s096t36_b0824900_m002022_m01011"
    "s096t20_b0824900_m002022_m01011"
    )
    min_trajs=(
        "0 100 100 100"                 "  0   0   0   0 0 0 0 0 0 0 0 0" "  0   0   0"
        "0   0   0   0"                 "  0   0   0   0 0 0 0 0 0 0 0 0" "200 200 200 200"
        "0   0   0   0 0 0 0 0 0 0 0 0" "700 100 400 400"                 "175 175"
        "0   0   0   0 0 0 0 0 0 0 0 0" "200 300 100 100"                 "0 0 0 0"
        "150 150 150 150"
    )
    MC_stepsize=10
fi


(
    cd "$(dirname "$0")" || exit

    for idx in "${!arr_conftypes[@]}"; do
        conftype=${arr_conftypes[idx]}
        min_conf="--min_conf ${min_trajs[idx]}"

        mycmd="
    ../_2_reduce_data.py $add_args --MC_stepsize $MC_stepsize $min_conf --qcdtype $qcdtype --conftype $conftype --corr $corr
    --basepath $basepath_work_data  --basepath_plot $basepath_plot --n_proc $nproc
    "
        # uncomment these lines to confirm each script call
        #    echo "$mycmd"
        #    echo -en "\n y/n? "
        #    read -r input
        #    if [ "$input" == "y" ]; then
        eval $mycmd
        #    fi

    done
    wait

)
