# Model and analytic evidence

This is a synthetic practice calculation. The sole physical input source is `problem.md`; no parameters are calibrated, fitted or measured. Temperatures below are Celsius, while temperature differences are kelvins.

## Requirements and route

The targets are the two threshold times, heat removed for each design, the speed comparison and its mechanism, the dimensionless threshold relation, the stipulated ±10% conductance sensitivity, a physical limitation, and a complete English manuscript. These are enumerated in `requirements.csv`.

The governing process and all parameters are supplied. The mechanism route uses the exact solution rather than adding unidentifiable physics. A direct numerical integration is retained only as an implementation self-check. There is no deadline, team assignment, selected A/B problem or experimental task in this practice.

## System, assumptions and event

The system boundary surrounds the sealed instrument. Define positive outward heat flow as P = G(T - Ta), and removed heat as Q(t) = integral from 0 to t of P(s) ds. Time zero is the supplied initial state. The threshold event is the first downward crossing of T* = 30 C, starting from T0 = 80 C with Ta = 20 C. With C > 0 and G > 0, this event is unique.

The stipulated law assumes a single uniform temperature, constant heat capacity and conductance, a fixed ambient temperature, and no net internal heat generation or other unmodeled energy transfer. These are properties of the prescribed model, not experimentally verified claims. Sealed means no mass exchange; it does not mean thermally insulated.

## Derivation

Let x = T - Ta. Since C dx/dt = -Gx, integration with x(0) = T0 - Ta yields

    T(t) = Ta + (T0 - Ta) exp(-Gt/C).

It satisfies the initial value and has dT/dt = -(G/C)(T - Ta). Setting T = T* gives

    t* = (C/G) ln[(T0 - Ta)/(T* - Ta)] = (C/G) ln 6.

The branch is physical because 20 < 30 < 80 and all conductances, including endpoints, are positive. Integrating the original energy equation, rather than depending on a cooling-time estimate, gives

    Q* = -C integral(T0 to T*) dT = C(T0 - T*) = 60000 J.

At the same target temperature the final energy change is fixed. G controls the rate of heat removal, not this total heat.

## Dimensionless relation and sensitivity

Let theta = (T - Ta)/(T0 - Ta) and u = Gt/C. Then dtheta/du = -theta, theta(0) = 1, and theta = exp(-u). Thus

    theta* = 1/6,  u* = Gt*/C = -ln(theta*) = ln 6.

The heat-capacity/conductance ratio C/G has units of seconds. The logarithm is dimensionless. G(T - Ta) has units J/s and the integrated heat has units J. An additive Celsius-to-kelvin temperature shift leaves every difference unchanged.

For a conductance scenario G' = G(1 + delta), holding C and temperatures fixed,

    t*'/t* = 1/(1 + delta),  (t*' - t*)/t* = -delta/(1 + delta),
    d ln(t*) / d ln(G) = -1.

The exact changes for delta = -0.1 and +0.1 are +11.111...% and -9.0909...%. They are deterministic endpoints, not confidence intervals, standard deviations or measured errors. Q* is unchanged. The 12 W/K design is faster for every independent pair of permitted endpoint/interior conductances: its minimum G is 10.8 W/K, exceeding the other design's maximum 8.8 W/K.

## Limiting and structural checks (author self-check)

- For positive G and T > Ta, dT/dt < 0, with no overshoot below ambient in the exact solution.
- At t = 0, T = 80 C; at large positive time, T tends to 20 C. At t*, Q* = 60 kJ, below the asymptotic 72 kJ available relative to ambient.
- As G tends to zero from above, t* tends to infinity. At G = 0 the target is never reached. As T* tends to Ta from above, the time diverges. As T* tends to T0 from below, the time tends to zero.
- For fixed C and temperatures, increasing G by a factor 1.5 reduces time by 1/1.5. It does not reduce the energy required to reach the target.
- These checks establish consistency of the stipulated model. They cannot show that a real instrument is spatially uniform or has constant conductance.

## Validity limits

If internal heat redistribution is slow compared with heat transfer to the surroundings, a surface may cool faster than the interior and one scalar temperature cannot represent both. Then reaching a surface temperature of 30 C would not establish that the whole instrument had reached 30 C. Geometry and thermal properties are absent, so the uniform-temperature assumption cannot be checked empirically or quantitatively here. A changing ambient, internal operating heat, temperature-dependent C or G, and additional nonlinear heat transfer could also alter the result. No numerical magnitude for those effects can be inferred from this problem.

## Numerical reproduction and acceptance criteria

`data/inputs.json` contains only stipulated values, specified scenario endpoints and check settings. `src/solve.py` calculates the exact values with the Python standard library and separately integrates dT/dt = -G(T-Ta)/C and dQ/dt = G(T-Ta), starting at T0 and Q = 0. RK4 uses steps (C/G)/10, (C/G)/20 and (C/G)/40. On the step crossing 30 C, bisection on a partial RK4 step localizes the event with a time-bracket width below 1e-11 s. The run has a 100000-step safety limit and raises an error if the event is missing.

Acceptance criteria set in `data/inputs.json`: exact threshold substitution residual below 1e-10 K; finest-step time error below 1e-4 s versus the exact formula; heat error below 1e-5 J; event-time errors decrease under the two halvings; 12 W/K design's worst permitted time is below 8 W/K design's best permitted time. All six conductance scenarios must pass. Full-precision results are saved in CSV/JSON; displayed table values are rounded only at presentation.

The RK4 calculation checks a separate implementation of the same stipulated differential law. It does not supply independent physical evidence or experimental validation, and a flux/temperature invariant preserved by this integrator is not an independent test of the real system.
