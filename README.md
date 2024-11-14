# Wind Farm Wake Steering
Investigation of the optimisation of individual yaw angles to maximise holistic wind farm output

## Files
- [exploration.ipynb](exploration.ipynb) - Exploration of the impact of parameters such as yaw, wind speed and wind direction on cost and utilisation
- [optimisation.ipynb](optimisation.ipynb) - Optimisation of yaw values for different wind and site conditions to reduce cost

N.B. `.html` version of some files exist to see output of notebooks once run

## Glossary
| Term | Meaning |
|---|---|
| Levelised Cost of Energy (LCoE) | Average cost per unit of energy produced over the lifetime of the project |
| Capacity factor | Amount of energy created as a proportion of total possible if asset operated at maximum capacity |

## To investigate
- Increase speed and direction resolution
    - Fix oscillations around rated wind speed
- Larger wind farms
- Impact of varying baseline turbulence
- Real time steering values
    - CNN
    - [Lookup table/surrogate model](https://adaptive.readthedocs.io/en/latest/algorithms_and_examples.html#examples)
- Off design performance
    - Local variations in speed and direction
    - Measured using LiDAR
- Curtailment of front turbines as well as steering
