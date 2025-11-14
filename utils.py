
def format_nombre_fr(nombre):
    try:
        if nombre is None: val = 0.0
        else: val = float(nombre)
        s_formate = "{:_.2f}".format(val)
        s_formate = s_formate.replace('_', ' ')
        s_formate = s_formate.replace('.', ',')
        return s_formate
    except (ValueError, TypeError): return str(nombre)
