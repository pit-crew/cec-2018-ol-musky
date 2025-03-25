select t.name,
   count(*) total,
   sum(case when deposit_amt = 0 then 1 else 0 end) empty,
   sum(case when deposit_amt > 0 then 1 else 0 end) active
from mcp_team t,
   mcp_site s
where s.team_id = t.token
group by s.team_id
order by t.name;
