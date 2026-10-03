"""Spherical calculations shared by estimation and storage validation."""
import math
RADIUS=6371000

def destination(anchor,distance_meters,bearing_degrees):
    lon,lat=map(math.radians,anchor);bearing=math.radians(bearing_degrees);delta=distance_meters/RADIUS
    end_lat=math.asin(math.sin(lat)*math.cos(delta)+math.cos(lat)*math.sin(delta)*math.cos(bearing))
    end_lon=lon+math.atan2(math.sin(bearing)*math.sin(delta)*math.cos(lat),math.cos(delta)-math.sin(lat)*math.sin(end_lat))
    return [(math.degrees(end_lon)+180)%360-180,math.degrees(end_lat)]

def meters_between(a,b):
    lon1,lat1,lon2,lat2=map(math.radians,(*a,*b));h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return RADIUS*2*math.asin(min(1,math.sqrt(h)))
