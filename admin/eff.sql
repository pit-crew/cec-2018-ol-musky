select t.name,
   sum(b.deposit_amt) as ore_available,
   sum(b.deposit_amt)-sum(s.deposit_amt) as ore_mined
from mcp_team t,
   mcp_belt b,
   mcp_site s
where b.sector_id = s.sector_id
   and s.team_id = t.token
group by s.team_id;
