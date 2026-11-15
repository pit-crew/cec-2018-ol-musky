"""Game engine: the rules of the MCP as a library with no I/O.

The engine holds no clock and no database. A caller gives it the active Scenario,
a TeamState, the current week, and a random number generator.

Time model
----------
The engine moves a team forward one week at a time (`rules.advance`), with or
without requests from the team. In each week:

1. Work orders that are due complete, in the sequence of their due week.
2. Each active hub mines for the weeks since it last mined.

Thus a hub that becomes active in week W gets its first ore in week W + 1, and
ore sells at the price of the week in which the shipment arrives.
"""
