import logging

import numpy as np
from py_wake.deficit_models import FugaDeficit, NoWakeDeficit, ZongGaussianDeficit
from py_wake.deflection_models import FugaDeflection, JimenezWakeDeflection
from py_wake.examples.data.hornsrev1 import (
    Hornsrev1Site,
    V80,
    wt9_x,
    wt9_y,
    wt16_x,
    wt16_y,
    wt_x,
    wt_y,
)
from py_wake.rotor_avg_models import CGIRotorAvg
from py_wake.superposition_models import LinearSum
from py_wake.turbulence_models import STF2017TurbulenceModel
from py_wake.wind_farm_models import All2AllIterative, PropagateDownwind
from scipy import optimize

# loads cost values
# capex and opex https://atb.nrel.gov/electricity/2023/index
# technology lifespans https://atb.nrel.gov/electricity/2023/definitions#costrecoveryperiod
# downtime https://blog.windurance.com/the-truth-about-pitch-system-downtime and https://energyfollower.com/how-long-do-wind-turbines-last/
CAPEX_GW = (3150 + 3901) / 2 * 1e6
_opex1 = (0.29, 102)
_opex2 = (0.46, 116)
_grad = (_opex2[1] - _opex1[1]) / (_opex2[0] - _opex1[0])
OPEX_FIXED_GWy = (_opex1[1] - _grad * _opex1[0]) * 1e6
OPEX_VAR_GWh = _grad / (365.25 * 24)
LIFESPAN = 30
DOWNTIME = 0.02

# define default ranges
WS_DEFAULT = np.arange(0, 31)
WD_DEFAULT = np.arange(0, 360, 15)

# load farm models
wfm_high = All2AllIterative(
    site=Hornsrev1Site(),
    windTurbines=V80(),
    wake_deficitModel=FugaDeficit(),
    superpositionModel=LinearSum(),
    deflectionModel=FugaDeflection(),
    turbulenceModel=STF2017TurbulenceModel(),
    rotorAvgModel=CGIRotorAvg(7),
)
wfm_low = PropagateDownwind(
    site=Hornsrev1Site(),
    windTurbines=V80(),
    wake_deficitModel=ZongGaussianDeficit(use_effective_ws=True),
    superpositionModel=LinearSum(),
    deflectionModel=JimenezWakeDeflection(),
    turbulenceModel=STF2017TurbulenceModel(),
    rotorAvgModel=None,
)
wfm_lossless = PropagateDownwind(
    site=Hornsrev1Site(),
    windTurbines=V80(),
    wake_deficitModel=NoWakeDeficit(),
    superpositionModel=LinearSum(),
    deflectionModel=None,
    turbulenceModel=None,
    rotorAvgModel=None,
)


# run simulation
def run_sim(wfm, x, y, yaw, ws, wd):
    sim_res = wfm(
        x=x,
        y=y,
        tilt=0,
        yaw=yaw,
        n_cpu=1,
        ws=ws,
        wd=wd,
    )
    return sim_res


# calculate metrics
def calc_metrics(sim_res, sim_res_base, Sector_frequency, P, show=False):
    # unpack values
    rated_power = (
        sim_res.windFarmModel.windTurbines.powerCtFunction.power_ct_tab[0].max() / 1e9
    )
    sim_res_base = sim_res_base.sel(wd=sim_res.wd)
    Sector_frequency = Sector_frequency.sel(wd=sim_res.wd)
    P = P.sel(wd=sim_res.wd)

    # calculate turbulent kinetic energy ratio
    tke_vel = ((sim_res.TI_eff * sim_res.ws) ** 2 * P).sum(["wd", "ws"])
    tke_vel_base = ((sim_res_base.TI_eff * sim_res_base.ws) ** 2 * P).sum(["wd", "ws"])
    tke_ratio = tke_vel / tke_vel_base

    # calculate metrics of interest
    uptime = 1 - DOWNTIME * tke_ratio
    aep = (sim_res.Power * P).sum("ws") * 8760 / 1e9 * uptime
    fixed_cost = (OPEX_FIXED_GWy + CAPEX_GW / LIFESPAN) * rated_power * Sector_frequency
    variable_cost = OPEX_VAR_GWh * aep
    lcoe = (fixed_cost + variable_cost) / (aep * 1000)
    cap_fac = aep / (
        Sector_frequency * rated_power * (sim_res.wt * 0 + 1) * 365.25 * 24
    )

    # print values
    if show:
        _, _, lcoe_overall, cap_fac_overall = aggregate_metrics(
            aep, lcoe, cap_fac, Sector_frequency
        )
        print(f"AEP [GWh]: {aep.sum():,.3f}")
        print(f"LCoE [USD/MWh]: {lcoe_overall:,.3f}")
        print(f"Capacity factor [%]: {100*cap_fac_overall:,.3f}")

    return aep, lcoe, cap_fac


# combination simulation and evaluation
def run_sim_and_calculate_metrics(
    sim_res_base,
    Sector_frequency,
    P,
    wfm,
    x,
    y,
    yaw,
    ws,
    wd,
    show=False,
):
    sim_res = run_sim(wfm=wfm, x=x, y=y, yaw=yaw, ws=ws, wd=wd)
    return calc_metrics(
        sim_res=sim_res,
        sim_res_base=sim_res_base,
        Sector_frequency=Sector_frequency,
        P=P,
        show=show,
    )


# aggregate metrics
def aggregate_metrics(aep=None, lcoe=None, cap_fac=None, Sector_frequency=None):
    # lcoe
    if aep is not None and lcoe is not None:
        lcoe_direction = (lcoe * (aep * 1000)).sum("wt") / (aep * 1000).sum("wt")
        lcoe_overall = (lcoe * (aep * 1000)).sum(["wt", "wd"]) / (aep * 1000).sum(
            ["wt", "wd"]
        )
    else:
        lcoe_direction = None
        lcoe_overall = None
    # cap_fac
    if cap_fac is not None and Sector_frequency is not None:
        cap_fac_direction = cap_fac.weighted(Sector_frequency).mean("wt")
        cap_fac_overall = cap_fac.weighted(Sector_frequency).mean(["wt", "wd"])
    else:
        cap_fac_direction = None
        cap_fac_overall = None

    return lcoe_direction, cap_fac_direction, lcoe_overall, cap_fac_overall


# define constants
YAW_SCALE = 30


# optimise for a single direction
def optimise_direction(
    wfm, x, y, ws, wd, sim_res_base, Sector_frequency, P, lcoe_direction_base
):

    # define constants
    ws = sim_res_base.ws.values.tolist()
    yaw_shape = (len(sim_res_base.wt), 1, len(ws))
    cut_in_index = np.argmax(
        sim_res_base.windFarmModel.windTurbines.power(sim_res_base.ws) > 0
    )
    cut_in_speed = sim_res_base.ws[cut_in_index].values.tolist()

    # optimise for power output across independent wind speeds
    logging.info("starting power based optimisation")
    yaw_opt_power = np.full(yaw_shape, np.nan)
    next_x0 = np.ones(len(sim_res_base.wt)) / YAW_SCALE
    for i, ws_ in enumerate(sim_res_base.ws.values):
        if ws_ >= cut_in_speed:
            # define objective function for power
            def obj_power_single(yaw_norm):
                sim_res = run_sim(
                    wfm=wfm, x=x, y=y, yaw=yaw_norm * YAW_SCALE, ws=ws_, wd=wd
                )
                power = sim_res.Power.sel(ws=ws_, wd=wd).sum("wt")
                power_base = sim_res_base.Power.sel(ws=ws_, wd=wd).sum("wt")
                obj = -(power / power_base).values.tolist()
                return obj

            res = optimize.minimize(fun=obj_power_single, x0=next_x0)
            next_x0 = res.x
            yaw_opt_power[:, :, i] = res.x.reshape(-1, 1) * YAW_SCALE
        else:
            yaw_opt_power[:, :, i] = np.zeros((len(sim_res_base.wt), 1))

    # define objective function for lcoe
    def obj_lcoe_single(yaw_norm):
        sim_res = run_sim(
            wfm=wfm, x=x, y=y, yaw=yaw_norm.reshape(yaw_shape) * YAW_SCALE, ws=ws, wd=wd
        )
        aep, lcoe, _ = calc_metrics(
            sim_res=sim_res,
            sim_res_base=sim_res_base,
            Sector_frequency=Sector_frequency,
            P=P,
        )
        _, _, lcoe_overall, _ = aggregate_metrics(
            aep=aep, lcoe=lcoe, Sector_frequency=Sector_frequency
        )
        obj = (lcoe_overall / lcoe_direction_base).values.tolist()
        return obj

    # optimise for lcoe across all wind speeds
    logging.info("starting LCoE based optimisation")
    res = optimize.minimize(
        fun=obj_lcoe_single,
        x0=yaw_opt_power.ravel() / YAW_SCALE,
        method="SLSQP",
        tol=1e-4,
    )
    yaw_opt_lcoe = res.x.reshape(yaw_shape) * YAW_SCALE

    return yaw_opt_power, yaw_opt_lcoe
