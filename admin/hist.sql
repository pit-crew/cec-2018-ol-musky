-- Histogram of the belt deposits in bands of 10 000 tonnes; one # for each 10 sectors.
SELECT (deposit_amt / 10000) * 10000        AS deposit,
       printf('%.*c', COUNT(*) / 10, '#')   AS sectors
FROM   mcp_belt
WHERE  deposit_amt > 0
GROUP  BY deposit;
