function report = matlab_smoke(outputDir)
%MATLAB_SMOKE Base-MATLAB synthetic research check; no contest holdout data.
% Checked with base MATLAB R2026b on macOS; rerun in each target environment.
% The target directory must not exist, to preserve previous research outputs.
if nargin == 0
    outputDir = fullfile(pwd, 'matlab-smoke-output');
end
if exist(outputDir, 'file') || exist(outputDir, 'dir')
    error('upc:ExistingOutput', 'Output target already exists.');
end
[ok, message] = mkdir(outputDir);
assert(ok, 'upc:CreateOutput', '%s', message);
m = 1; c = 0.4; k = 4;
tgrid = linspace(0, 10, 1001).';
gamma = c/(2*m);
wd = sqrt(k/m-gamma^2);
xexact = exp(-gamma*tgrid).*(cos(wd*tgrid)+gamma/wd*sin(wd*tgrid));
rtols = [1e-6; 1e-8; 1e-10];
errors = zeros(size(rtols));
for j = 1:numel(rtols)
    opts = odeset('RelTol', rtols(j), 'AbsTol', rtols(j)*1e-2);
    [t, y] = ode45(@(~, s) [s(2); -(c*s(2)+k*s(1))/m], tgrid, [1; 0], opts);
    assert(numel(t) == numel(tgrid) && all(isfinite(y(:))), ...
        'upc:IncompleteSolve', 'Incomplete or nonfinite ODE output.');
    errors(j) = max(abs(y(:,1)-xexact));
end
energy = 0.5*m*y(:,2).^2 + 0.5*k*y(:,1).^2;
assert(errors(end) < 1e-6, 'upc:AnalyticMismatch', 'Analytic displacement check failed.');
assert(max(diff(energy)) < 1e-8, 'upc:EnergyMismatch', 'Energy increase exceeds tolerance.');
publishedPoles = roots([1, -1.9, 0.88]);
assert(max(abs(publishedPoles)) > 1, 'upc:PoleMismatch', 'Unstable-coefficient check failed.');
writetable(table(t, y(:,1), y(:,2), energy, xexact, ...
    'VariableNames', {'t_s','x_m','v_m_s','energy_J','x_exact_m'}), ...
    fullfile(outputDir, 'trajectory.csv'));
writetable(table(rtols, errors, 'VariableNames', {'RelTol','max_x_error_m'}), ...
    fullfile(outputDir, 'tolerance-study.csv'));
report = struct('case_type', 'synthetic damped oscillator', ...
    'release', version('-release'), 'x_10_m', y(end,1), ...
    'x_10_exact_m', xexact(end), 'max_x_error_m', errors(end), ...
    'max_energy_step_J', max(diff(energy)), ...
    'published_poles', publishedPoles.', 'checks_passed', true);
fid = fopen(fullfile(outputDir, 'validation.json'), 'w');
assert(fid ~= -1, 'upc:FileOpen', 'Could not open validation output.');
cleanupFile = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(report));
clear cleanupFile;
fig = figure('Visible', 'off');
cleanupFigure = onCleanup(@() close(fig));
subplot(2,1,1); plot(t, y(:,1), '-', t, xexact, '--');
xlabel('Time (s)'); ylabel('Displacement (m)'); legend('ODE45', 'Analytic'); grid on;
subplot(2,1,2); plot(t, energy);
xlabel('Time (s)'); ylabel('Mechanical energy (J)'); grid on;
if exist('exportgraphics', 'file')
    exportgraphics(fig, fullfile(outputDir, 'trajectory.png'), 'Resolution', 160);
else
    print(fig, fullfile(outputDir, 'trajectory.png'), '-dpng', '-r160');
end
disp(report);
end
