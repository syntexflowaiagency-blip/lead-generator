from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

geolocator = Nominatim(user_agent='quill-labs-lead-generator-v2')
_COORDS_CACHE = {}


def get_coords_by_location(location: str) -> list[str]:
    '''
    `location: str` - specific location, neighborhood, or city name

    Returns a list of coordinate strings: [latitude, longitude]
    Includes fallback resolution so sub-localities never crash the scraper.
    '''
    loc_clean = location.strip()
    if loc_clean in _COORDS_CACHE:
        return _COORDS_CACHE[loc_clean]

    # Try specific location first
    try:
        loc = geolocator.geocode(loc_clean, timeout=5)
        if loc:
            coords = [str(loc.latitude), str(loc.longitude)]
            _COORDS_CACHE[loc_clean] = coords
            return coords
    except (GeocoderTimedOut, GeocoderServiceError, Exception):
        pass

    # Try parent city if specific area fails (e.g. "Bandra, Mumbai, India" -> "Mumbai, India")
    parts = [p.strip() for p in loc_clean.split(",") if p.strip()]
    if len(parts) > 1:
        parent_loc = ", ".join(parts[1:])
        try:
            loc = geolocator.geocode(parent_loc, timeout=5)
            if loc:
                coords = [str(loc.latitude), str(loc.longitude)]
                _COORDS_CACHE[loc_clean] = coords
                return coords
        except Exception:
            pass

    # Ultimate default fallback (Mumbai central)
    fallback = ["19.0760", "72.8777"]
    _COORDS_CACHE[loc_clean] = fallback
    return fallback
