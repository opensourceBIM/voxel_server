from __future__ import print_function

import os
import time
import numpy
import string
import threading
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
        
def get_voxelfile(id, num):
    assert not (set(id) - set(string.ascii_letters))
    db = os.path.join(tempfile.gettempdir(), id, "%d.vox" % int(num))
    return voxel_storage.load(db)

application.url_map.converters['color'] = ColorConverter

D = {}
lock = threading.Lock()

IDENTITY = lambda *args: None

def run_voxelfile(cwd, id, oncomplete=IDENTITY, args=None):
    def make_args(d):
        for kv in d.items():
            if kv[1] is True:
                yield "--%s" % kv[0]
            else:
                yield "--%s=%s" % kv
        
    li = []
    di = defaultdict(dict)
    D[id] = {'id': id, 'lines': li, 'dict': di}
    proc = subprocess.Popen([os.environ.get("VOXEC_EXE") or "voxec", "voxelfile.txt", "--threads=8"] + list(make_args(args or {})), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while True:
        ln = proc.stderr.readline().decode('utf-8')
        if not ln:
            if proc.poll() is None:
                time.sleep(0.5)
                continue
            else: 
                break
        with lock:
            if ln.startswith('@'):
                attrs = list(map(lambda s: s.strip(), ln.split(';')))
                id = int(attrs[0][1:])
                for a in attrs[1:]:
                    k, v = map(lambda s: s.strip(), a.split(':'))
                    di[id][k] = v
            li.append(ln)
    oncomplete()
            
def dispatch(cwd, id, oncomplete=IDENTITY, args=None):
    t = threading.Thread(target=run_voxelfile, args=(cwd, id, oncomplete, args))
    t.start()
    
def dispatch_or_run(asynch, *args):
    return [run_voxelfile, dispatch][asynch](*args)

from visualisation import create_image, image_builder
from storage import voxel_storage

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
    pairs = zip(parts[0::2], parts[1::2])
    
    for num, clr in pairs:
        num = int(num)
        clr = ColorConverter.to_python(clr)
        
        vox = get_voxelfile(id, num)
        
        cs = getattr(vox, 'chunksize', -1)
        
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
    
@application.route('/run', methods=['POST'])
def run_post():
    
    id = "".join(choice(string.ascii_letters) for i in range(32))
    d = os.path.join(tempfile.gettempdir(), id)
    os.makedirs(d)
    
    for file in request.files.getlist('ifc'):
        file.save(os.path.join(d, secure_filename(file.filename)))
        
    with open(os.path.join(d, "voxelfile.txt"), "w") as f:
        # normalize line endings
        for ln in request.form["voxelfile"].splitlines():
            f.write(ln + "\n")
        
    dispatch(d, id)
        
    return render_template('run_progress.html', context_id=id)
    
   
class voxelfile_base(View):
    """
    A base view for methods that take an IFC file as input,
    which is processed using a voxelfile.
    """
    
    size = 0.05
    args = {}
    oncomplete = IDENTITY
    
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
        last = sorted(map(int, di.keys()))[-1]
        return int(di.get(last).get('count')) * self.size ** self.dim
        
    def finalize(self):
        di = D.get(id).get('dict')
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
    name = "volume"
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
        d = os.path.join(tempfile.gettempdir(), self.id)
        ifn = os.path.join(d, "23.obj")
        ofn = os.path.join(d, "buffer.bin")
        prepared_buffer.create(ifn, ofn)

    def finalize(self):
        return jsonify({"id": self.id})
        
@application.route('/safetybarriers/<id>/annotation')
@cross_origin()
def get_safetybarriers_annotation(id):
    assert not (set(id) - set(string.ascii_letters))
    fn = os.path.join(tempfile.gettempdir(), id, "buffer.bin")
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
    
application.add_url_rule('/gross_floor_area', methods=['GET', 'POST'], view_func=gross_floor_area.as_view('gross_floor_area'))
application.add_url_rule('/outer_surface_area', methods=['GET', 'POST'], view_func=outer_surface_area.as_view('outer_surface_area'))
application.add_url_rule('/volume', methods=['GET', 'POST'], view_func=volume.as_view('volume'))
application.add_url_rule('/safetybarriers/create', methods=['GET', 'POST'], view_func=safety_barriers.as_view('safety_barriers'))

@application.route('/progress/<id>', methods=['GET'])
def get_progress(id):
    with lock:
        p = D.get(id)
    return jsonify(p)
    
if __name__ == "__main__":
    application.run(host='0.0.0.0')
