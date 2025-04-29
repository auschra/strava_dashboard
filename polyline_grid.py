import math

# Decode a Google encoded polyline string into a list of (lat, lon) pairs
def decode_polyline(polyline_str):
    index, lat, lng, coordinates = 0, 0, 0, []
    changes = {'lat': 0, 'lng': 0}

    while index < len(polyline_str):
        for key in ['lat', 'lng']:
            shift, result = 0, 0
            while True:
                b = ord(polyline_str[index]) - 63
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            if (result & 1):
                changes[key] = ~(result >> 1)
            else:
                changes[key] = (result >> 1)
        lat += changes['lat']
        lng += changes['lng']
        coordinates.append((lat / 1e5, lng / 1e5))
    return coordinates

def snap_to_grid(coords, precision=4):
    """
    Snap each (lat, lon) to a grid by rounding to the given decimal precision.
    4 decimals ~ 10m, 3 decimals ~ 100m
    """
    return [(
        round(lat, precision),
        round(lon, precision)
    ) for lat, lon in coords]

def route_grid_signature(polyline, precision=4):
    coords = decode_polyline(polyline)
    grid_points = snap_to_grid(coords, precision)
    # Use set to ignore duplicate points, but keep order for route shape
    seen = set()
    signature = []
    for pt in grid_points:
        if pt not in seen:
            seen.add(pt)
            signature.append(pt)
    return tuple(signature)

# Compare two route signatures: if their sets overlap by > threshold, consider them the same
def routes_similar(sig1, sig2, jaccard_threshold=0.7):
    set1, set2 = set(sig1), set(sig2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    if union == 0:
        return False
    jaccard = intersection / union
    return jaccard >= jaccard_threshold