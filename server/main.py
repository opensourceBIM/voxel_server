from __future__ import print_function

import os
import time
import json
import numpy
import string
import threading
import functools
import subprocess
import tempfile

from random import SystemRandom
choice = lambda seq: SystemRandom().choice(seq)

from collections import defaultdict

from flask import Flask, request, send_file, render_template, jsonify, abort
from flask.views import View
from flask_cors import cross_origin
from werkzeug.utils import secure_filename
from werkzeug.routing import BaseConverter
from tempfile import NamedTemporaryFile

application = Flask(__name__)

class ColorConverter(BaseConverter):
    @staticmethod
    def to_python(value):
        def _():
            for n in range(len(value)//2):
                yield int(value[2*n:2*n+2], base=16)
        x = tuple(_())
        print("COLOR", x)
        return x
    @staticmethod
    def to_url(values):
        return ''.join(map(lambda i: hex(i)[0:2], values))
        
def get_voxelfile(id, num, lazy=False):
    assert not (set(id) - set(string.ascii_letters))
    db = os.path.join(tempfile.gettempdir(), id, "%d.vox" % int(num))
    return voxel_storage.load(db, lazy)

application.url_map.converters['color'] = ColorConverter

IDENTITY = lambda *args: None

def run_voxelfile(cwd, id, oncomplete=IDENTITY, args=None):
    def make_args(d):
        for kv in d.items():
            if kv[1] is True:
                yield "--%s" % kv[0]
            else:
                yield "--%s=%s" % kv

    f = open(os.path.join(cwd, "progress"), "wb")
    proc = subprocess.check_call([
        os.environ.get("VOXEC_EXE") or "voxec", 
        "-q", "--log-file", "log.json",
        "voxelfile.txt", 
        "--threads=8"
    ] + list(make_args(args or {})),
        cwd=cwd, 
        stdout=f
    )

    oncomplete()
            
def dispatch(cwd, id, oncomplete=IDENTITY, args=None):
    t = threading.Thread(target=run_voxelfile, args=(cwd, id, oncomplete, args))
    t.start()
    
def dispatch_or_run(asynch, *args):
    return [run_voxelfile, dispatch][asynch](*args)

from visualisation import create_image, image_builder
from storage import voxel_storage, harmonize

@application.route('/2d/<id>/<num>', methods=['GET'])
@application.route('/2d/<id>/<orientation>/<num>', methods=['GET'])
def serve_2d(id, num, orientation='z'):
    vox = get_voxelfile(id, num)
    return render_template('2d.html', context=id, num=num, chunks=list(vox.numchunks), chunksize=vox.chunksize, orientation=orientation)

@application.route('/3d/<id>/<num>', methods=['GET'])
def serve_3d(id, num):
    vox = get_voxelfile(id, num)
    return render_template('3d.html', context=id, num=num, chunks=list(vox.numchunks), chunksize=vox.chunksize)
    
@application.route('/slice/<id>/<num>/<orientation>/<offset>', methods=['GET'])
def get_slice(id, num, orientation, offset, step="final"):
    vox = get_voxelfile(id, num)
    
    cs = getattr(vox, 'chunksize', -1)
    im = create_image(vox, "xyz".index(orientation), int(offset), grid=cs)
    
    tmp = NamedTemporaryFile(suffix='png')
    im.save(tmp, 'PNG')
    tmp.seek(0,0)
    
    return send_file(tmp, mimetype="image/png")
    
@application.route('/count_slice/<id>/<num>/<orientation>/<offset>', methods=['GET'])
def count_slice(id, num, orientation, offset, step="final"):
    vox = get_voxelfile(id, num)
    key = [slice(None)] * 3
    axis = "xyz".index(orientation)
    key[axis] = int(offset)
    N = numpy.count_nonzero(vox[tuple(key)])
    return jsonify({"count": N})
    
# Safety barrier example:
# http://localhost:5000/multi_slice/eeeeee/z/64/4/888888/17/aaaaff/21/ffdddd/23/ff0000
# More recent ids:
# http://localhost:5000/multi_slice/eeeeee/x/280/4/888888/16/aaaaff/18/5555ff/22/ffdddd/24/ff0000

@application.route('/multi_slice/<id>/<color:color>/<orientation>/<offset>/<path:slices>')
def multi_slice(id, color, orientation, offset, slices):
    b = image_builder(color)
    
    cs = 0
    
    parts = slices.split('/')
    pairs = list(zip(parts[0::2], parts[1::2]))
    
    ids = range(100)
    ids_used = set(int(n) for n, _ in pairs)
    print("ids_used", ids_used)
    
    def get_voxelfile_safe(*args):
        try:
            return get_voxelfile(*args)
        except FileNotFoundError as e:
            pass        
    
    voxs = dict(filter(lambda tup: tup[1] is not None, map(lambda i: (i, get_voxelfile_safe(id, i, i not in ids_used)), ids)))
    print(voxs)
    voxs_new = harmonize(voxs.values())
    voxs = dict(zip(voxs.keys(), voxs_new))
    
    for num, clr in pairs:
        num = int(num)
        clr = ColorConverter.to_python(clr)
        
        vox = voxs[num]
        cs = getattr(vox, 'chunksize', -1)
        print(type(vox))
        
        b.add(vox, "xyz".index(orientation), int(offset), clr)
        
    if cs:
        b.grid(cs)
        
    im = b.image()
    
    tmp = NamedTemporaryFile(suffix='png')
    im.save(tmp, 'PNG')
    tmp.seek(0,0)
    
    return send_file(tmp, mimetype="image/png")

@application.route('/run', methods=['GET'])
def run_get():
    return render_template('run.html')
    
@application.route('/run', defaults={'sync':'async'}, methods=['POST'])
@application.route('/run/<sync>', methods=['POST'])
def run_post(sync):
    
    id = "".join(choice(string.ascii_letters) for i in range(32))
    d = os.path.join(tempfile.gettempdir(), id)
    os.makedirs(d)
    
    for file in request.files.getlist('ifc'):
        file.save(os.path.join(d, secure_filename(file.filename)))
        
    with open(os.path.join(d, "voxelfile.txt"), "w") as f:
        # normalize line endings
        for ln in request.form["voxelfile"].splitlines():
            f.write(ln + "\n")
        
    dispatch_or_run(sync == 'async', d, id)
    
    if request.accept_mimetypes.accept_html:
        return render_template('run_progress.html', context_id=id)
    else:
        return jsonify({'id': id})
    
   
class voxelfile_base(View):
    """
    A base view for methods that take an IFC file as input,
    which is processed using a voxelfile.
    """
    
    size = 0.05
    args = {}
    onbegin = IDENTITY
    oncomplete = IDENTITY
    
    @cross_origin()
    def dispatch_request(self):
        if request.method == 'POST':
            self.id = id = "".join(choice(string.ascii_letters) for i in range(32))
            d = os.path.join(tempfile.gettempdir(), id)
            os.makedirs(d)
            
            file = request.files["ifc"]
            file.save(os.path.join(d, "input.ifc"))
                
            with open(os.path.join(d, "voxelfile.txt"), "w") as f:
                f.write(self.command)
                
            args = {"size": self.size}
            args.update(self.args)
            
            self.onbegin()
            
            dispatch_or_run(self.asynch, d, id, self.oncomplete, args)
            
            return self.finalize()
        else:
            return render_template('form.html')
            
class scalar_voxelfile_base(voxelfile_base):
    """
    A base view for tasks that result in a numeric measure as output.
    """
    
    asynch = False
    
    def get_result(self, di):
        if len(di) == 0:
            # The dictionary is empty when geometry generation
            # failed. In which case, likely the entity types in
            # question were not found. Perhaps we need to handle
            # this differently in subtypes, for now just return
            # zero.
            return 0.
        last = sorted(map(int, di.keys()))[-1]
        return int(di.get(last).get('count')) * self.size ** self.dim
        
    def finalize(self):
        di = D.get(self.id).get('dict')
        return jsonify({self.name: self.get_result(di)})
        
class gross_floor_area(scalar_voxelfile_base):
    name = "floor_area"
    dim = 2
    command = """file = parse("input.ifc")
slabss = create_geometry(file, include={"IfcSlab"})
roofss = create_geometry(file, include={"IfcRoof"})
slabs = voxelize(slabss)
roofs = voxelize(roofss)
floors_surface = subtract(slabs, roofs)
floor_volume = volume2(floors_surface)
floors = union(floors_surface, floor_volume)
floors_surface = collapse(floors, 0, 0, -1)
num = count(floors_surface)
"""

class outer_surface_area(scalar_voxelfile_base):
    name = "surface_area"
    dim = 2
    command = """file = parse("input.ifc")
surfaces = create_geometry(file)
voxels = voxelize(surfaces)
fixed_voxels = fill_gaps(voxels)
offset_voxels = offset(fixed_voxels)
outmost_voxels = outmost(offset_voxels)
result = count(outmost_voxels)
"""

class volume(scalar_voxelfile_base):
    name = "volume"
    size = 0.01
    dim = 3
    command = """file = parse("input.ifc")
surfaces = create_geometry(file)
voxels = voxelize(surfaces)
volume = volume2(voxels)
"""
    def get_result(self, di):
        # Count (inner volume) full and surface voxels half
        surface = int(di.get(2).get('count')) 
        volume = int(di.get(3).get('count'))
        return ((surface // 2) + volume) * self.size ** self.dim
        
class safety_barriers(voxelfile_base):
    asynch = True    
    name = "safety_barriers"
    args = {"mesh": True}
    command = """file = parse("input.ifc")
surfaces = create_geometry(file, exclude={"IfcOpeningElement", "IfcDoor", "IfcSpace"})
slabs = create_geometry(file, include={"IfcSlab"})
doors = create_geometry(file, include={"IfcDoor"})
surface_voxels = voxelize(surfaces)
slab_voxels = voxelize(slabs)
door_voxels = voxelize(doors)
walkable = shift(slab_voxels, dx=0, dy=0, dz=1)
walkable_minus = subtract(walkable, slab_voxels)
walkable_seed = intersect(door_voxels, walkable_minus)
surfaces_sweep = sweep(surface_voxels, dx=0, dy=0, dz=0.5)
surfaces_padded = offset_xy(surface_voxels, 0.1)
surfaces_obstacle = sweep(surfaces_padded, dx=0, dy=0, dz=-0.5)
walkable_region = subtract(surfaces_sweep, surfaces_obstacle)
walkable_seed_real = subtract(walkable_seed, surfaces_padded)
reachable = traverse(walkable_region, walkable_seed_real)
reachable_shifted = shift(reachable, dx=0, dy=0, dz=1)
reachable_bottom = subtract(reachable, reachable_shifted)
reachable_padded = offset_xy(reachable_bottom, 0.2)
full = constant_like(surface_voxels, 1)
surfaces_sweep_1m = sweep(surface_voxels, dx=0, dy=0, dz=1.0)
deadly = subtract(full, surfaces_sweep_1m)
really_reachable = subtract(reachable_padded, surfaces_obstacle)
result = intersect(really_reachable, deadly)
"""

    def oncomplete(self):
        import prepared_buffer
        import annotation_data
        d = os.path.join(tempfile.gettempdir(), self.id)
        ifc = os.path.join(d, "input.ifc")
        ifn = os.path.join(d, "23.obj")
        ofn1 = os.path.join(d, "buffer.bin")
        ofn2 = os.path.join(d, "data.json")
        prepared_buffer.create(ifn, ofn1)
        annotation_data.create(ifc, ifn, ofn2)

    def finalize(self):
        return jsonify({"id": self.id})


class evacuationroutes(voxelfile_base):
    asynch = True    
    size = 0.1
    name = "evacuation_routes"
    args = {"mesh": True}
    command = """file = parse("input.ifc")
fire_door_filter = filter_attributes(file, OverallWidth=">1.2")
surfaces = create_geometry(file, exclude={"IfcOpeningElement", "IfcDoor", "IfcSpace"})
slabs = create_geometry(file, include={"IfcSlab"})
doors = create_geometry(file, include={"IfcDoor"})
fire_doors = create_geometry(fire_door_filter, include={"IfcDoor"})
surface_voxels = voxelize(surfaces)
slab_voxels = voxelize(slabs)
door_voxels = voxelize(doors)
fire_door_voxels = voxelize(fire_doors)
walkable = shift(slab_voxels, dx=0, dy=0, dz=1)
walkable_minus = subtract(walkable, slab_voxels)
walkable_seed = intersect(door_voxels, walkable_minus)
surfaces_sweep = sweep(surface_voxels, dx=0, dy=0, dz=0.5)
surfaces_padded = offset_xy(surface_voxels, 0.1)
surfaces_obstacle = sweep(surfaces_padded, dx=0, dy=0, dz=-0.5)
walkable_region = subtract(surfaces_sweep, surfaces_obstacle)
walkable_seed_real = subtract(walkable_seed, surfaces_padded)
reachable = traverse(walkable_region, walkable_seed_real)
reachable_shifted = shift(reachable, dx=0, dy=0, dz=1)
reachable_bottom = subtract(reachable, reachable_shifted)
all_surfaces = create_geometry(file)
voxels = voxelize(all_surfaces)
external = exterior(voxels)
walkable_region_offset = offset_xy(walkable_region, 1)
walkable_region_incl = union(walkable_region, walkable_region_offset)
seed_external = intersect(walkable_region_incl, external)
seed_fire_doors = intersect(walkable_region_incl, fire_door_voxels)
seed = union(seed_external, seed_fire_doors)
safe = traverse(walkable_region_incl, seed, 30.0, connectedness=26)
safe_bottom = intersect(safe, reachable_bottom)
unsafe = subtract(reachable_bottom, safe)
safe_interior = subtract(safe_bottom, external)
x = mesh(unsafe, "unsafe.obj")
x = mesh(safe_interior, "safe.obj")
"""

    def oncomplete(self):
        import prepared_buffer
        import annotation_data
        d = os.path.join(tempfile.gettempdir(), self.id)
        ifc = os.path.join(d, "input.ifc")
        ifn1 = os.path.join(d, "safe.obj")
        ifn2 = os.path.join(d, "unsafe.obj")
        ofn1 = os.path.join(d, "buffer.bin")
        ofn2 = os.path.join(d, "data.json")
        prepared_buffer.create(ofn1, ifn1, '0f0', ifn2, 'f00')
        annotation_data.create(ifc, ifn2, ofn2)

    def finalize(self):
        return jsonify({"id": self.id})
        

class accessibility(voxelfile_base):
    asynch = True    
    name = "evacuation_routes"
    args = {"mesh": True}
    command = """file = parse("input.ifc")
surfaces = create_geometry(file, exclude={"IfcOpeningElement", "IfcDoor", "IfcSpace"})
slabs = create_geometry(file, include={"IfcSlab"})
doors = create_geometry(file, include={"IfcDoor"})
surface_voxels = voxelize(surfaces)
slab_voxels = voxelize(slabs)
door_voxels = voxelize(doors)
walkable = shift(slab_voxels, dx=0, dy=0, dz=1)
walkable_minus = subtract(walkable, slab_voxels)
walkable_seed = intersect(door_voxels, walkable_minus)
surfaces_sweep = sweep(surface_voxels, dx=0, dy=0, dz=2)
surfaces_padded = offset_xy(surface_voxels, 0.1)
surfaces_obstacle = sweep(surfaces_padded, dx=0, dy=0, dz=-0.5)
walkable_region = subtract(surfaces_sweep, surfaces_obstacle)
walkable_seed_real = subtract(walkable_seed, surfaces_padded)
reachable = traverse(walkable_region, walkable_seed_real)
reachable_below = shift(slab_voxels, dx=0, dy=0, dz=-1)
void = dump_surfaces(reachable_below, surfaces, "surfaces")
"""

    def onbegin(self):
        # Create an empty directory for the dump_surfaces() call 
        os.makedirs(os.path.join(tempfile.gettempdir(), self.id, "surfaces"))

    def oncomplete(self):
        import prepared_buffer
        import get_surfaces
        d = os.path.join(tempfile.gettempdir(), self.id)
        ifc = os.path.join(d, "input.ifc")
        surfaces = os.path.join(d, "surfaces")
        ofn1 = os.path.join(d, "buffer.bin")
        
        get_surfaces.get_surfaces(surfaces, ifc)
        prepared_buffer.create(ifn, ofn1)

    def finalize(self):
        return jsonify({"id": self.id})
        
        
@application.route('/<check_type>/<id>/<part>')
@cross_origin()
def get_file(check_type, id, part):
    if len(set(id) - set(string.ascii_letters)) != 0:
        abort(404)
    if check_type not in {"safetybarriers", "evacuationroutes", "run"}:
        abort(404)
    p = {
        "annotation": "buffer.bin",
        "metadata": "data.json"
    }.get(part)
    if p is None:
        pfn = os.path.abspath(os.path.join(tempfile.gettempdir(), id, part))
        if os.path.exists(pfn) and os.path.dirname(pfn) == os.path.join(tempfile.gettempdir(), id):
            p = part
        else:
            abort(404)
    fn = os.path.join(tempfile.gettempdir(), id, p)
    if not os.path.exists(fn):
        abort(404)
    return send_file(fn, mimetype="application/octet-stream")


@application.route('/safetybarriers/<id>/progress')
@cross_origin()
def get_safetybarriers_progress(id):
    assert not (set(id) - set(string.ascii_letters))
    d = os.path.join(tempfile.gettempdir(), id)
    progress = 0
    for p in os.listdir(d):
        if p.endswith(".vox.contents"): progress += 5
    return jsonify({"progress": progress})
    
    
# TODO: progress for evacuationroutes
    
application.add_url_rule('/gross_floor_area', methods=['GET', 'POST'], view_func=gross_floor_area.as_view('gross_floor_area'))
application.add_url_rule('/outer_surface_area', methods=['GET', 'POST'], view_func=outer_surface_area.as_view('outer_surface_area'))
application.add_url_rule('/volume', methods=['GET', 'POST'], view_func=volume.as_view('volume'))
application.add_url_rule('/safetybarriers/create', methods=['GET', 'POST'], view_func=safety_barriers.as_view('safety_barriers'))
application.add_url_rule('/evacuationroutes/create', methods=['GET', 'POST'], view_func=evacuationroutes.as_view('evacuationroutes'))

@application.route('/progress/<id>', methods=['GET'])
def get_progress(id):
    return jsonify(os.path.getsize(os.path.join(tempfile.gettempdir(), id, "progress")))
    
@application.route('/log/<id>', methods=['GET'])
def get_log(id):
    lines = []
    try:
        with open(os.path.join(tempfile.gettempdir(), id, "log.json")) as f:
            for l in f:
                try: lines.append(json.loads(l))
                except Exception as e: print(e)
    except FileNotFoundError as e:
        abort(503)
    return jsonify(lines)

if __name__ == "__main__":
    application.run(host='0.0.0.0')
