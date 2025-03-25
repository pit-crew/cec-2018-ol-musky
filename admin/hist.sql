SELECT ROUND(deposit_amt, -4)    AS deposit,
       RPAD('', COUNT(*)/10, '#') AS sectors
FROM   mcp_belt
WHERE  deposit_amt > 0
GROUP  BY deposit;
