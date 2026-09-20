def render_sales(rows):
    out = []
    for name, qty, price in rows:
        total = qty * price
        out.append(f"{name:<12}{qty:>5}{price:>10.2f}{total:>12.2f}")
    grand = sum(q * p for _, q, p in rows)
    out.append(f"{'TOTAL':<12}{'':>5}{'':>10}{grand:>12.2f}")
    return "\n".join(out)

def render_refunds(rows):
    out = []
    for name, qty, price in rows:
        total = qty * price
        out.append(f"{name:<12}{qty:>5}{price:>10.2f}{total:>12.2f}")
    grand = sum(q * p for _, q, p in rows)
    out.append(f"{'TOTAL':<12}{'':>5}{'':>10}{grand:>12.2f}")
    return "REFUNDS\n" + "\n".join(out)

def render_inventory(rows):
    out = []
    for name, qty, price in rows:
        total = qty * price
        out.append(f"{name:<12}{qty:>5}{price:>10.2f}{total:>12.2f}")
    grand = sum(q * p for _, q, p in rows)
    out.append(f"{'TOTAL':<12}{'':>5}{'':>10}{grand:>12.2f}")
    return "INVENTORY\n" + "\n".join(out)
