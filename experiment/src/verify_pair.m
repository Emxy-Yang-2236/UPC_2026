function verify_pair(pair_path, output_path)
% Independent base MATLAB integration from fitted initial states, all lengths in m.
p = jsondecode(fileread(pair_path));
assert(~isfile(output_path),'Choose a new output filename');
q = zeros(2,2); dt = zeros(2,1); dq = dt; early = dt;
for i = 1:2
    s = p.shots(i);
    acceleration = @(v) [0;0;-p.g_m_s2] - s.kappa_per_m*norm(v)*v + cross(s.beta_per_s(:),v);
    rhs = @(t,x) [x(4:6); acceleration(x(4:6))];
    options = odeset('RelTol',1e-10,'AbsTol',1e-12,'Events',@crossings,'MaxStep',0.01);
    sol = ode45(rhs,[0 1],[p.start_m(:);s.velocity0_m_s(:)],options);
    assert(isequal(sol.ie(end),1));
    x = deval(sol,p.times_s);
    early(i) = max(abs(x(1:3,:)' - p.readings_m),[],'all');
    q(i,:) = sol.ye(2:3,end)';
    dq(i) = norm(q(i,:)-s.goal_yz_m(:)');
    dt(i) = abs(sol.xe(end)-s.arrival_s);
end
assert(all(dq<0.003 & dt<0.0002 & early<1e-6));
result = struct('version',version,'goal_yz_m',q,'early_max_m',early,'difference_m',dq,'difference_s',dt,'status','pass');
fid = fopen(output_path,'wt'); assert(fid~=-1);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(result,'PrettyPrint',true));
end

function [value,isterminal,direction] = crossings(~,x)
value = [x(1)-11;x(3)-0.11]; isterminal = [1;1]; direction = [1;-1];
end
