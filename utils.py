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

# loads cost values
# capex and opex https://atb.nrel.gov/electricity/2023/index
# technology lifespans - https://atb.nrel.gov/electricity/2023/definitions#costrecoveryperiod
CAPEX_GW = (3150 + 3901) / 2 * 1e6
OPEX_GWy = (102 + 116) / 2 * 1e6
LIFESPAN = 30


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
def run_sim(wfm=wfm_low, x=wt9_x, y=wt9_y, yaw=0, ws=np.arange(0, 31)):
    sim_res = wfm(
        x=x,
        y=y,
        tilt=0,
        yaw=yaw,
        n_cpu=None,
        ws=ws,
        wd=270,
    )
    return sim_res


# calculate metrics
def calc_metrics(sim_res, show=False):
    nt = len(sim_res.wt)
    power_installed = (
        sim_res.windFarmModel.windTurbines.powerCtFunction.power_ct_tab[0].max()
        / 1e9
        * nt
    )
    lcoe = (
        (OPEX_GWy + CAPEX_GW / LIFESPAN)
        * power_installed
        / (sim_res.aep().sum().values * 1000)
    )
    cap_fac = sim_res.aep().sum().values / (power_installed * 365.25 * 24) * 100
    if show:
        print(f"LCoE [USD/MWh]: {lcoe:,.3f}")
        print(f"Capacity factor [%]: {cap_fac:,.2f}")
    return lcoe, cap_fac
