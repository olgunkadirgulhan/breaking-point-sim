"""Breaking Point Sim sahne üretici (Blender 4.5, rigid body + Cycles).
blender -b --factory-startup -P scene.py -- params.json out_dir

params.json: {"kind": "wall|tower|pyramid|dominoes", "seed": int, "frames": int, "spp": int, ...}
Çıktı: out_dir/f_####.png kareler + out_dir/meta.json (sayılar, çarpma karesi, kare başı çarpışma şiddeti → ses)."""
import bpy, sys, json, math, random, os
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
P = json.load(open(argv[0])); OUT = argv[1]; os.makedirs(OUT, exist_ok=True)
rng = random.Random(P['seed'])
FR = P.get('frames', 360); SPP = P.get('spp', 16)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
for t in ('OPTIX', 'CUDA'):
    try:
        prefs.compute_device_type = t; prefs.get_devices()
        if any(d.type == t for d in prefs.devices): break
    except Exception: pass
for d in prefs.devices: d.use = d.type == prefs.compute_device_type
gpu = [d.name for d in prefs.devices if d.use and d.type != 'CPU']
print('DEVICES', prefs.compute_device_type if gpu else 'CPU', gpu, flush=True)
sc.cycles.device = 'GPU' if gpu else 'CPU'; sc.cycles.samples = SPP; sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.05
sc.cycles.use_denoising = True
try:   # OptiX kartında GPU gürültü giderici (CPU'daki OIDN 1080p'de kare başı saniyeler yiyor)
    if prefs.compute_device_type == 'OPTIX': sc.cycles.denoiser = 'OPTIX'
    else: sc.cycles.denoiser = 'OPENIMAGEDENOISE'; sc.cycles.denoising_use_gpu = True
except Exception: pass
sc.cycles.max_bounces = 4; sc.cycles.diffuse_bounces = 2; sc.cycles.glossy_bounces = 2; sc.cycles.transmission_bounces = 2
sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
sc.render.use_persistent_data = True
sc.render.resolution_x, sc.render.resolution_y = P.get('res', (1080, 1920)); sc.render.fps = 30
sc.frame_start, sc.frame_end = 1, FR
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'; sc.view_settings.exposure = -0.4

bpy.ops.rigidbody.world_add(); W = sc.rigidbody_world
W.substeps_per_frame = 30; W.solver_iterations = 20; W.point_cache.frame_end = FR
W.time_scale = P.get('time_scale', 0.5)              # ağır çekim: fizik gerçek hızın yarısında akar
RB = W.collection


# ---------- malzemeler (hepsi prosedürel; dış dosya yok) ----------
def principled(name, col, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1); b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    return m, b, m.node_tree


def noisy(name, col, rough, scale=8.0, var=0.25, metal=0.0, bump=0.15):
    """renk + pürüz gürültüsü + kabartma: düz plastik görünümü kırar"""
    m, b, nt = principled(name, col, rough, metal)
    tc = nt.nodes.new('ShaderNodeTexCoord'); nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 8
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.inputs['Factor'].default_value = var
    mix.inputs['A'].default_value = (*col, 1); mix.inputs['B'].default_value = tuple(c * 0.55 for c in col) + (1,)
    nt.links.new(nz.outputs['Fac'], mix.inputs['Factor']); nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = bump
    nt.links.new(nz.outputs['Fac'], bp.inputs['Height']); nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m


def wood(name, col):
    m, b, nt = principled(name, col, 0.6)
    tc = nt.nodes.new('ShaderNodeTexCoord'); wv = nt.nodes.new('ShaderNodeTexWave'); wv.wave_type = 'RINGS'
    wv.inputs['Scale'].default_value = 3.0; wv.inputs['Distortion'].default_value = 6; wv.inputs['Detail'].default_value = 4
    nt.links.new(tc.outputs['Object'], wv.inputs['Vector'])
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
    mix.inputs['A'].default_value = (*col, 1); mix.inputs['B'].default_value = tuple(c * 0.6 for c in col) + (1,)
    nt.links.new(wv.outputs['Fac'], mix.inputs['Factor']); nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    return m


BALLS = {'steel': ((0.62, 0.63, 0.66), 0.22, 1.0), 'gold': ((0.95, 0.68, 0.25), 0.18, 1.0),
         'copper': ((0.86, 0.45, 0.3), 0.25, 1.0), 'black iron': ((0.06, 0.06, 0.07), 0.45, 1.0),
         'wood': ((0.55, 0.36, 0.2), 0.65, 0.0), 'aluminium': ((0.8, 0.81, 0.83), 0.3, 1.0), 'lead': ((0.3, 0.31, 0.33), 0.55, 1.0),
         'rubber': ((0.05, 0.05, 0.05), 0.8, 0.0)}

# ---------- zemin, gökyüzü, ışık ----------
bpy.ops.mesh.primitive_plane_add(size=200); fl = bpy.context.object
fl.data.materials.append(noisy('concrete', (0.2, 0.195, 0.185), 0.85, scale=2.5, var=0.35, bump=0.3))
bpy.context.view_layer.objects.active = fl; bpy.ops.rigidbody.object_add(); fl.rigid_body.type = 'PASSIVE'; fl.rigid_body.friction = 0.8

w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; nt = w.node_tree
sky = nt.nodes.new('ShaderNodeTexSky')
try: sky.sky_type = 'NISHITA'
except Exception: pass
sun_el = math.radians(P.get('sun_el', rng.uniform(12, 40))); sun_az = math.radians(P.get('sun_az', rng.uniform(0, 360)))
try:
    sky.sun_elevation = sun_el; sky.sun_rotation = sun_az; sky.air_density = rng.uniform(0.8, 1.6); sky.dust_density = rng.uniform(0.5, 3)
except Exception: pass
nt.links.new(sky.outputs['Color'], nt.nodes['Background'].inputs['Color'])
nt.nodes['Background'].inputs['Strength'].default_value = 0.18
bpy.ops.object.light_add(type='SUN'); sun = bpy.context.object; sun.data.energy = 2.2; sun.data.angle = math.radians(1.5)
sun.rotation_euler = (math.pi / 2 - sun_el, 0, sun_az + math.pi / 2)


def add_rb(o, mass, friction=0.6, bounce=0.05, shape='BOX'):
    bpy.context.view_layer.objects.active = o; o.select_set(True)
    bpy.ops.rigidbody.object_add(); r = o.rigid_body
    r.mass = mass; r.friction = friction; r.restitution = bounce; r.collision_shape = shape
    r.use_margin = True; r.collision_margin = 0.002; r.linear_damping = 0.04; r.angular_damping = 0.1
    o.select_set(False)
    return o


def box(loc, size, mat, rot=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object
    o.scale = size; bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); o.rotation_euler.z = rot
    bev = o.modifiers.new('b', 'BEVEL'); bev.width = min(size) * 0.06; bev.segments = 2
    o.data.materials.append(mat)
    return o


def projectile(radius, start, hit, hit_frame, mass, matname):
    """kinematik başlar, hit_frame'de serbest kalır: fizik motoru hızı devralır"""
    col, rough, metal = BALLS[matname]
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=start, segments=64, ring_count=32); b = bpy.context.object
    bpy.ops.object.shade_smooth()
    b.data.materials.append(noisy(matname, col, rough, scale=30, var=0.12, metal=metal, bump=0.05))
    add_rb(b, mass, 0.5, 0.1, 'SPHERE'); b.rigid_body.kinematic = True
    b.keyframe_insert('location', frame=1); b.location = hit; b.keyframe_insert('location', frame=hit_frame)
    for fc in b.animation_data.action.fcurves:
        for k in fc.keyframe_points: k.interpolation = 'LINEAR'
    b.rigid_body.keyframe_insert('kinematic', frame=hit_frame); b.rigid_body.kinematic = False
    b.rigid_body.keyframe_insert('kinematic', frame=hit_frame + 1)
    return b


bodies = []; meta = {'kind': P['kind'], 'seed': P['seed']}
K = P['kind']; HF = P.get('hit_frame', 26); ball = None


def appr(default):
    """yaklaşma mesafesi: istenen çarpma hızı (m/s, simülasyon zamanında) × kinematik süre"""
    v = P.get('speed', default); return v * HF * W.time_scale / sc.render.fps

if K == 'wall':
    rows, cols = P['rows'], P['cols']; bw, bh, bd = 0.25, 0.075, 0.12
    bm = noisy('brick', P.get('brick_col', (0.33, 0.09, 0.05)), 0.9, scale=14, var=0.4, bump=0.4)
    grid = {}
    for r in range(rows):
        off = bw / 2 if r % 2 else 0
        for c in range(cols):
            x = (c - cols / 2) * bw + off
            o = box((x, 0, bh / 2 + r * bh + 0.0005), (bw * 0.97, bd, bh * 0.95), bm, rng.uniform(-0.008, 0.008))
            bodies.append(add_rb(o, 2.2 * (bw * bd * bh) / (0.25 * 0.12 * 0.075), 0.75)); grid[r, c] = (o, x)
    if P.get('mortar'):   # harç: komşu tuğlalar arasında kırılabilir sabit bağ (eşik = dayanım)
        thr = P['mortar'] * P.get('mortar_max', 60.0); ncon = 0
        for (r, c), (o, x) in grid.items():
            pairs = [grid.get((r, c + 1))] + [grid[r + 1, c2] for c2 in range(cols) if (r + 1, c2) in grid and abs(grid[r + 1, c2][1] - x) < bw * 0.99]
            for q in filter(None, pairs):
                bpy.ops.object.empty_add(location=(o.location + q[0].location) / 2); e = bpy.context.object
                bpy.ops.rigidbody.constraint_add(); k = e.rigid_body_constraint
                k.type = 'FIXED'; k.object1 = o; k.object2 = q[0]; k.use_breaking = True; k.breaking_threshold = thr; ncon += 1
        meta['bonds'] = ncon
    top = rows * bh; R = P['ball_r']; hh = top * P.get('hit_h', 0.45); d = appr(10)
    ball = projectile(R, (0, -bd / 2 - R + 0.05 - d, hh), (0, -bd / 2 - R + 0.05, hh), HF, P['ball_mass'], P['ball_mat'])
    meta.update(count=rows * cols, label=f'{rows * cols} BRICKS', target_h=top)
elif K == 'tower':
    layers = P['layers']; L, Wd, H = 0.6, 0.2, 0.12
    wm = wood('wood', P.get('wood_col', (0.62, 0.42, 0.24)))
    for l in range(layers):
        for i in (-1, 0, 1):
            if l % 2: o = box((i * Wd, 0, H / 2 + l * H), (Wd * 0.97, L, H * 0.97), wm, rng.uniform(-0.01, 0.01))
            else: o = box((0, i * Wd, H / 2 + l * H), (L, Wd * 0.97, H * 0.97), wm, rng.uniform(-0.01, 0.01))
            bodies.append(add_rb(o, 0.45, 0.55))
    top = layers * H; R = P['ball_r']; hh = top * P.get('hit_h', 0.3)
    d = appr(10); hit = Vector((-L / 2 - R + 0.05, -0.15, hh)); dv = Vector((-0.91, -0.41, 0))
    ball = projectile(R, tuple(hit + dv * d), tuple(hit), HF, P['ball_mass'], P['ball_mat'])
    meta.update(count=layers * 3, label=f'{layers * 3}-BLOCK TOWER', target_h=top)
elif K == 'pyramid':
    n = P['base']; s = 0.5
    wm = wood('crate', P.get('wood_col', (0.55, 0.38, 0.2)))
    cnt = 0
    for lv in range(n):
        k = n - lv
        for i in range(k):
            for j in range(k):
                o = box(((i - (k - 1) / 2) * s, (j - (k - 1) / 2) * s, s / 2 + lv * s), (s * 0.96,) * 3, wm, rng.uniform(-0.01, 0.01))
                bodies.append(add_rb(o, 8, 0.6)); cnt += 1
    top = n * s; R = P['ball_r']
    ball = projectile(R, (0.4, -0.3, top + 7), (0.2, -0.1, top + R * 0.6), HF, P['ball_mass'], P['ball_mat'])   # yukarıdan düşer
    meta.update(count=cnt, label=f'{cnt} CRATES', target_h=top)
elif K == 'dominoes':
    n = P['count']; dw, dh, dd = 0.1, 0.3, 0.03; gap = 0.16
    cols = [(0.85, 0.12, 0.1), (0.95, 0.75, 0.1), (0.1, 0.35, 0.85), (0.1, 0.6, 0.3), (0.92, 0.92, 0.9)]
    mats = [noisy(f'dom{i}', c, 0.35, scale=20, var=0.06, bump=0.02) for i, c in enumerate(cols)]
    a, turns = 0.22, P.get('turns', 3.5)                    # Arşimet spirali: dıştan içe
    th_max = turns * 2 * math.pi; pts = []; th = th_max
    while th > 0.8 and len(pts) < n:
        r = a * th; pts.append((r * math.cos(th), r * math.sin(th), th))
        th -= gap / max(r, 0.3)
    for i, (x, y, th) in enumerate(pts):
        tang = math.atan2(math.cos(th) * a * th + math.sin(th) * a, -math.sin(th) * a * th + math.cos(th) * a)
        o = box((x, y, dh / 2 + 0.001), (dd, dw, dh), mats[(i // 12) % len(mats)], tang)
        bodies.append(add_rb(o, 0.05, 0.4))
    x0, y0, th0 = pts[0]; tang0 = math.atan2(math.cos(th0) * a * th0 + math.sin(th0) * a, -math.sin(th0) * a * th0 + math.cos(th0) * a)
    d0 = Vector((math.cos(tang0), math.sin(tang0), 0))
    R = 0.06
    ball = projectile(R, tuple(Vector((x0, y0, dh * 0.8)) + d0 * 3), tuple(Vector((x0, y0, dh * 0.8)) + d0 * (dd / 2 + R)), HF, 0.4, P['ball_mat'])
    meta.update(count=len(pts), label=f'{len(pts)} DOMINOES', target_h=dh)
elif K == 'rain':   # N çelik bilye ahşap kulenin üstüne yağar
    layers = P.get('layers', 16); L, Wd, H = 0.6, 0.2, 0.12
    wm = wood('wood', P.get('wood_col', (0.62, 0.42, 0.24)))
    for l in range(layers):
        for i in (-1, 0, 1):
            if l % 2: o = box((i * Wd, 0, H / 2 + l * H), (Wd * 0.97, L, H * 0.97), wm, rng.uniform(-0.01, 0.01))
            else: o = box((0, i * Wd, H / 2 + l * H), (L, Wd * 0.97, H * 0.97), wm, rng.uniform(-0.01, 0.01))
            bodies.append(add_rb(o, 0.45, 0.55))
    top = layers * H; n = P['count']; R = P.get('bead_r', 0.05)
    col, rough, metal = BALLS[P.get('ball_mat', 'steel')]
    bm = noisy('bead', col, rough, scale=40, var=0.1, metal=metal, bump=0.03)
    sp = 2.3 * R; side = max(1, math.ceil(math.sqrt(min(n, 64))))
    for i in range(n):
        lv, k = divmod(i, side * side)
        x = (k % side - (side - 1) / 2) * sp + rng.uniform(-0.2, 0.2) * R
        y = (k // side - (side - 1) / 2) * sp + rng.uniform(-0.2, 0.2) * R
        bpy.ops.mesh.primitive_uv_sphere_add(radius=R, location=(x, y, top + 1.2 + lv * sp), segments=20, ring_count=10)
        b = bpy.context.object; bpy.ops.object.shade_smooth(); b.data.materials.append(bm)
        bodies.append(add_rb(b, P.get('bead_mass', 4.0), 0.4, 0.3, 'SPHERE'))
    meta.update(count=layers * 3, label=f'{n} STEEL BALLS', target_h=top + 0.6)
    HF = int(math.sqrt(2 * 1.2 / 9.81) / W.time_scale * sc.render.fps)
else:
    raise SystemExit('bilinmeyen tür ' + K)

# ---------- kamera: yavaş yörünge, hedefe kilit ----------
tgt_z = meta['target_h'] * 0.45
bpy.ops.object.empty_add(location=(0, 0, tgt_z)); aim = bpy.context.object
CAMD = {'wall': (4.6, 0.5, 24), 'tower': (4.2, 0.6, 24), 'rain': (4.6, 1.0, 24), 'pyramid': (8.5, 1.2, 26), 'dominoes': (6.5, 5.0, 24)}[K]
dist = P.get('cam_dist', CAMD[0]); az0 = math.radians(P.get('cam_az', rng.uniform(-75, -35))); el = P.get('cam_el', CAMD[1])
bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.lens = P.get('lens', CAMD[2])
cam.data.dof.use_dof = True; cam.data.dof.focus_object = aim; cam.data.dof.aperture_fstop = 5.6
tr = cam.constraints.new('TRACK_TO'); tr.target = aim; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
for f, daz, dd in ((1, 0, 1.0), (FR, math.radians(P.get('orbit', 35)), 0.88)):
    cam.location = (dist * dd * math.cos(az0 + daz), dist * dd * math.sin(az0 + daz), el + tgt_z + (0.4 if f == FR else 0))
    cam.keyframe_insert('location', frame=f)
# hafif el titremesi yok: tripod hissi (gerçek laboratuvar çekimi değil, sim olduğu belli)

# ---------- bake + kare başı çarpışma şiddeti (ses için) ----------
bpy.ops.ptcache.bake_all(bake=True)
objs = bodies + ([ball] if ball else []); prev = None; pv = None; inten = []
for f in range(1, FR + 1):
    sc.frame_set(f)
    pos = [o.matrix_world.translation.copy() for o in objs]
    if prev is not None:
        vel = [(p - q).length for p, q in zip(pos, prev)]
        if pv is not None:
            e = sum(max(0.0, a - b) * o.rigid_body.mass ** 0.5 for a, b, o in zip(pv, vel, objs))   # yavaşlama = çarpışma
            inten.append(round(e, 4))
        else: inten.append(0.0)
        pv = vel
    else: inten.append(0.0)
    prev = pos
meta.update(frames=FR, fps=sc.render.fps, hit_frame=HF, time_scale=W.time_scale, intensity=inten,
            ball_mass=P.get('ball_mass'), ball_mat=P.get('ball_mat'))
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'))
print('META', json.dumps({k: v for k, v in meta.items() if k != 'intensity'}), flush=True)

sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 94
sc.render.filepath = os.path.join(OUT, 'f_')
if P.get('preview'):   # hızlı yerel kontrol: düşük çözünürlük, birkaç kare
    sc.render.resolution_percentage = 25; sc.cycles.samples = 8; sc.cycles.device = 'CPU'
    for f in P['preview']:
        sc.frame_set(f); sc.render.filepath = os.path.join(OUT, f'p_{f:04d}.jpg'); bpy.ops.render.render(write_still=True)
else:
    if P.get('lowres'):   # yerel uçtan uca test
        sc.render.resolution_percentage = 34; sc.cycles.samples = 6; sc.cycles.device = 'CPU'
    if P.get('fr_from'):  # paralel render: bu iş yalnızca kendi kare aralığını çizer (fizik yine baştan hesaplanır)
        sc.frame_start, sc.frame_end = P['fr_from'], P['fr_to']
    bpy.ops.render.render(animation=True)
