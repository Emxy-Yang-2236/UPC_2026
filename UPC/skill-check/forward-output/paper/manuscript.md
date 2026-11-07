# Cooling a Small Instrument: Time Scale, Energy Removal and Conductance Sensitivity

*An invented practice study; all numerical results are predictions of a stipulated model.*

## Abstract

We compare two thermal conductances for a uniform instrument cooling from 80 °C toward an ambient temperature of 20 °C. Solving the stipulated linear energy equation gives a time to 30 °C of 268.76 s for 8 W/K and 179.18 s for 12 W/K. Both designs remove 60.0 kJ by that temperature. The dimensionless threshold time is $Gt_*/C=\ln 6$; conductance changes the cooling rate without changing the energy difference between fixed endpoint temperatures. A ±10% conductance scenario gives time changes of +11.11% and −9.09%, and the faster design retains its ordering throughout these scenarios. A separate numerical implementation checks the exact calculation. No experimental evidence is supplied, so the results establish consistency with the stated model rather than physical calibration.

## 1. Problem and scope

The practice statement [1] specifies a sealed instrument with heat capacity $C=1200\ \mathrm{J/K}$, initial temperature $T_0=80\ ^\circ\mathrm C$, fixed ambient temperature $T_a=20\ ^\circ\mathrm C$, and constant conductance $G=8$ or $12\ \mathrm{W/K}$. Its temperature obeys

$$
C\frac{dT}{dt}=-G(T-T_a). \tag{1}
$$

We determine the first downward crossing of $T_*=30\ ^\circ\mathrm C$, the heat removed by that event, the speed comparison, and sensitivity to the stipulated conductance scenarios. No measured data or external calibration are available. We therefore answer this mathematical design comparison without estimating the behavior of an independently characterized instrument.

Equation (1) treats the entire body as having one temperature. It incorporates constant heat capacity, constant conductance, fixed ambient temperature and no additional net heat source. A sealed body can exchange heat while retaining its mass. These assumptions belong to the prescribed model; they have not been established by experiment.

## 2. Exact solution and controlling dimensionless relationship

Taking time zero at the initial state, separation of variables yields

$$
T(t)=T_a+(T_0-T_a)e^{-Gt/C}. \tag{2}
$$

For $G>0$ and $T_a<T_*<T_0$, cooling is monotonic and the threshold occurs once, at

$$
t_* = \frac{C}{G}\ln\!\left(\frac{T_0-T_a}{T_*-T_a}\right)
     = \frac{C}{G}\ln 6. \tag{3}
$$

Temperature differences have units of kelvins, whether expressed using Celsius or absolute temperature values. The logarithm in (3) is dimensionless, and $C/G$ is the cooling time scale in seconds.

Define normalized excess temperature $\theta=(T-T_a)/(T_0-T_a)$ and dimensionless time $u=Gt/C$. Equation (1) becomes $d\theta/du=-\theta$, with $\theta(0)=1$. Hence

$$
\theta=e^{-u},\qquad \theta_*=\frac16,
\qquad u_*=\frac{Gt_*}{C}=-\ln\theta_*=\ln6\simeq1.79176. \tag{4}
$$

Both designs follow the same normalized cooling curve; changing $G$ rescales physical time.

The positive outward heat flow is $P=G(T-T_a)$. Integrating (1) between the initial and threshold states gives

$$
Q_* = \int_0^{t_*}P\,dt=C(T_0-T_*)
     =1200(80-30)\ \mathrm J=60.0\ \mathrm{kJ}. \tag{5}
$$

Thus the endpoint temperatures fix the removed heat independently of conductance.

## 3. Design comparison and sensitivity

Table 1 contains exact-model calculations rounded for display. The central scenario times are 268.76 s (4.48 min) and 179.18 s (2.99 min). Increasing conductance from 8 to 12 W/K increases the heat-removal rate by a factor 1.5 at the same temperature. It therefore reduces the threshold time to two-thirds of the slower design's time, a reduction of 89.59 s or 33.33%.

**Table 1.** Times and heat removed to the same 30 °C threshold. The ±10% entries are stipulated deterministic conductance scenarios, not observations, confidence intervals or probability distributions. Other inputs remain fixed.

| Nominal $G$ (W/K) | Conductance change | Actual $G$ (W/K) | $t_*$ (s) | $Q_*$ (kJ) |
| ---: | ---: | ---: | ---: | ---: |
| 8 | −10% | 7.2 | 298.63 | 60.0 |
| 8 | 0% | 8.0 | 268.76 | 60.0 |
| 8 | +10% | 8.8 | 244.33 | 60.0 |
| 12 | −10% | 10.8 | 199.08 | 60.0 |
| 12 | 0% | 12.0 | 179.18 | 60.0 |
| 12 | +10% | 13.2 | 162.89 | 60.0 |

Writing a conductance scenario as $G'=G(1+\delta)$, equation (3) gives

$$
\frac{t_*'}{t_*}=\frac{1}{1+\delta},\qquad
\frac{t_*'-t_*}{t_*}=-\frac{\delta}{1+\delta},\qquad
\frac{d\ln t_*}{d\ln G}=-1. \tag{6}
$$

A 10% decrease in conductance lengthens time by 11.11%; a 10% increase shortens it by 9.09%. The asymmetry follows from the reciprocal dependence and is lost in a first-order ±10% approximation. The time ranges are 244.33–298.63 s and 162.89–199.08 s, respectively. Even the slowest permitted 12 W/K scenario is 45.25 s faster than the fastest permitted 8 W/K scenario. The ordering therefore holds for every independent pair of conductances in the stated ranges. Heat removal remains 60.0 kJ throughout.

## 4. Calculation checks and reproduction

The package provides the inputs in `data/inputs.json`, the standard-library Python calculation in `src/solve.py`, and full-precision results in `data/derived/results.csv`. Running `python src/solve.py` from the project directory regenerates the result table and checks.

An implementation separate from equation (2) advances the stipulated temperature ODE and outward heat flux using fourth-order Runge–Kutta. Time steps are $(C/G)/10$, $(C/G)/20$, and $(C/G)/40$; bisection on the final partial step localizes the threshold to a time-bracket width below $10^{-11}$ s. All six scenarios reach the event. At the finest step, the largest time difference from (3) is $9.86\times10^{-7}$ s, below the preset $10^{-4}$ s criterion. Errors decrease under both step halvings. The largest integrated-heat discrepancy is below $1.7\times10^{-10}$ J, compared with a $10^{-5}$ J criterion. Numerical details are saved in `data/derived/numerical_check.csv` and `summary.json`.

The exact solution also satisfies the initial condition, has the correct negative temperature derivative, and tends to ambient at long times. The threshold heat of 60 kJ is less than the 72 kJ that could be removed on asymptotic cooling to ambient. Equation (3) tends to zero as the threshold approaches the initial temperature and diverges as it approaches ambient or as $G\to0^+$. These are consistency and author self-checks. Both implementations assume the same physical law, so their agreement supplies no experimental validation.

## 5. Physical limitations

A real instrument may have a cooler surface and a warmer interior if internal heat redistribution is slow. A surface reaching 30 °C would then not imply that the whole instrument had reached 30 °C, and the single-temperature model would need replacement by a spatial or multi-body model. No geometry or material properties are supplied to quantify this limitation. Internal operating heat, temperature-dependent heat capacity or conductance, or a warming ambient could also change the prediction. The stated conductance scenarios explore one prescribed design parameter; they do not bound these omitted physical effects.

## 6. Conclusion

Under the stipulated uniform-body model, the 8 and 12 W/K designs reach 30 °C after 268.76 and 179.18 s and each remove 60.0 kJ. The mechanism is a fixed normalized temperature decay with time scale $C/G$, controlled by $Gt_*/C=\ln6$. The 12 W/K design remains faster throughout the ±10% conductance scenarios. These results fully answer the invented problem within its assumptions; applicability to a real instrument remains untested.

## Reference

[1] *Synthetic practice problem: cooling a small instrument*. Supplied invented statement, reproduced verbatim in `problem.md`. All parameters and the evolution law are stipulated there. No external physical parameter or literature result was used.

## Report on the Use of AI

An OpenAI Codex agent generated the derivation, calculation code, English manuscript and author self-check for this synthetic practice task. Exact deployed model/version metadata were not independently available in this run. The received task instruction is retained in `ai-records/task-input.txt`; the scope and gaps are described in `ai-records/coverage.md`. A complete host export of all visible interactions and tool outputs has not been captured, so this paragraph and the partial local records do **not** constitute a complete contest AI disclosure. No experimental data, independent reviewer, contest submission or award capability is claimed. No document was sent or uploaded.
