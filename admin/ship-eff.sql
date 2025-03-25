select t.name,
   count(*) total,
   sum(case when item='ship ore' then 1 else 0 end) ship,
   sum(case when item='sell ore' then 1 else 0 end) sell,
   sum(case when item='ore was pirated' then 1 else 0 end) pirated
from mcp_team t,
   mcp_ledger l
where l.team_id = t.token
group by l.team_id
order by t.name;
