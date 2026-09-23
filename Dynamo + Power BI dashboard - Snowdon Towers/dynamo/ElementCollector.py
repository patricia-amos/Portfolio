import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

clr.AddReference('RevitServices')
import RevitServices
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

# 1. Grab all element instances globally across the database background
collector = FilteredElementCollector(doc).WhereElementIsNotElementType()

physical_elements = []

geo_options = Options()
geo_options.DetailLevel = ViewDetailLevel.Coarse

# 2. Fully dynamic evaluation loop with exception handling
for elem in collector:
    if elem is None:
        continue
        
    cat = elem.Category
    if cat is None:
        continue # Drops non-graphical internal data maps
        
    # Check if this category belongs to the 3D Model environment
    if cat.CategoryType != CategoryType.Model:
        continue # Excludes annotations, schedules, views, and sheets
        
    # CRITICAL CHANGE: Skip Spatial Elements (Rooms/Spaces/Areas) completely 
    if isinstance(elem, SpatialElement):
        continue

    # 3. DEFENSIVE CHECK: Ensure the object actually supports geometry properties 
    if not hasattr(elem, "get_Geometry"):
        continue

    # 4. Geometry Check (Separates true physical volumes from lines/curves)
    geo_elem = elem.get_Geometry(geo_options)
    if geo_elem is None:
        continue
        
    has_solid = False
    for geo_obj in geo_elem:
        if isinstance(geo_obj, Solid) and geo_obj.Faces.Size > 0:
            has_solid = True
            break
        elif isinstance(geo_obj, GeometryInstance):
            instance_geo = geo_obj.GetInstanceGeometry()
            for sub_obj in instance_geo:
                if isinstance(sub_obj, Solid) and sub_obj.Faces.Size > 0:
                    has_solid = True
                    break
                    
    # 5. Keep only true physical volumes
    if has_solid:
        physical_elements.append(elem)

# Output clean instances directly to visual nodes
OUT = physical_elements


