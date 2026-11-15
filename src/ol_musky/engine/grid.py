"""Belt geometry. Sector IDs are row-major: sector_id = row * cols + col."""

_OFFSETS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if not (dr == dc == 0)]


def adjacent_sectors(sector_id: int, rows: int, cols: int) -> list[int]:
    """The sectors (8 or fewer) that touch the given sector. The belt does not wrap."""
    row, col = divmod(sector_id, cols)
    return [
        (row + dr) * cols + (col + dc)
        for dr, dc in _OFFSETS
        if 0 <= row + dr < rows and 0 <= col + dc < cols
    ]
