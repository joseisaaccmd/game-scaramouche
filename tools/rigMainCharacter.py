import bpy
import math
import os
import time
import numpy as np
from mathutils import Matrix, Vector

SRC_BLEND = r"C:\Users\asus2\Downloads\Scaramouche.blend"
OUT_GLB = r"D:\PROJECT WEB\utanomori-main\tools\mainCharacter_rigged.glb"
OUT_BLEND = r"D:\PROJECT WEB\utanomori-main\tools\mainCharacter_rigged.blend"

TARGET_HEIGHT = 4.77
FPS = 30


def log(*args):
    print(*args, flush=True)


def smoothstep(e0, e1, x):
    if e0 == e1:
        return 0.0 if x < e0 else 1.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def ensure_object_mode():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def activate_action(arm, action):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = action
    if hasattr(action, 'slots'):
        if len(action.slots) == 0:
            try:
                slot = action.slots.new(id_type='OBJECT', name=arm.name)
            except TypeError:
                slot = action.slots.new('OBJECT', arm.name)
            ad.action_slot = slot
        else:
            ad.action_slot = action.slots[0]
    return ad


def action_fcurves(action):
    curves = []
    if hasattr(action, 'fcurves'):
        curves.extend(action.fcurves)
    if hasattr(action, 'layers'):
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, 'channelbags'):
                    for bag in strip.channelbags:
                        curves.extend(bag.fcurves)
    return curves


def make_action(arm, name, frames, pose_fn):
    action = bpy.data.actions.new(name)
    activate_action(arm, action)
    bpy.context.view_layer.objects.active = arm

    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)

    for f in range(1, frames + 2):
        t = (f - 1) / frames
        pose = pose_fn(t)
        for bone_name, values in pose.items():
            pb = arm.pose.bones[bone_name]
            if 'rotation' in values:
                pb.rotation_euler = values['rotation']
                pb.keyframe_insert('rotation_euler', frame=f, group=bone_name)
            if 'location' in values:
                pb.location = values['location']
                pb.keyframe_insert('location', frame=f, group=bone_name)

    curves = action_fcurves(action)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    if hasattr(action, 'use_frame_range'):
        action.use_frame_range = True
        action.frame_start = 1
        action.frame_end = frames + 1
    log("ACTION", name, "frames", frames + 1, "fcurves", len(curves))
    return action


def idle_pose(t):
    a = math.sin(2.0 * math.pi * t)
    b = math.sin(2.0 * math.pi * t + 1.1)
    return {
        'hips': {
            'location': (0.0, 0.010 * a, 0.0),
            'rotation': (0.008 * a, 0.0, 0.018 * math.sin(2.0 * math.pi * t + 0.4)),
        },
        'head': {
            'rotation': (0.050 * a, 0.0, 0.070 * b),
        },
        'leg.L': {'rotation': (0.0, 0.0, 0.0)},
        'leg.R': {'rotation': (0.0, 0.0, 0.0)},
    }


def run_pose(t):
    a = math.sin(2.0 * math.pi * t)
    bob = 0.5 - 0.5 * math.cos(4.0 * math.pi * t)
    return {
        'hips': {
            'location': (0.0, 0.030 * bob, 0.0),
            'rotation': (0.0, 0.0, 0.022 * a),
        },
        'head': {
            'rotation': (-0.055 + 0.035 * math.sin(4.0 * math.pi * t + math.pi * 0.5), 0.0, 0.045 * a),
        },
        'leg.L': {'rotation': (0.46 * a, 0.0, 0.0)},
        'leg.R': {'rotation': (-0.46 * a, 0.0, 0.0)},
    }


def main():
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=SRC_BLEND)
    ensure_object_mode()

    # Remove the three unplaced preview icospheres (they are in glTF_not_exported and are not the
    # character's eyes - the eyes are baked into COLOR_0).
    for obj in list(bpy.data.objects):
        if obj.type == 'MESH' and obj.name.startswith('Icosphere'):
            bpy.data.objects.remove(obj, do_unlink=True)

    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    log("MESHES", len(meshes))

    # Bake the Sketchfab parent transforms into each mesh, then apply object transforms.
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # Combined vertex bbox from real vertices.
    all_co = []
    for o in meshes:
        n = len(o.data.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        o.data.vertices.foreach_get('co', co)
        all_co.append(co.reshape(n, 3))
    co = np.concatenate(all_co, axis=0)
    mn = co.min(axis=0)
    mx = co.max(axis=0)
    log("RAW_BBOX", mn, mx, "size", mx - mn)

    bottom = co[co[:, 2] < mn[2] + 0.15]
    cx = float((bottom[:, 0].min() + bottom[:, 0].max()) * 0.5)
    cy = float((bottom[:, 1].min() + bottom[:, 1].max()) * 0.5)
    min_z = float(mn[2])
    log("PIVOT_XZ", cx, cy, "MIN_Z", min_z)

    offset = Matrix.Translation((-cx, -cy, -min_z))
    height = float(mx[2] - mn[2])
    scale = TARGET_HEIGHT / height
    log("NORMALIZE offset", (-cx, -cy, -min_z), "height", height, "scale", scale)

    for o in meshes:
        o.data.transform(offset)
        o.data.transform(Matrix.Scale(scale, 4))
        o.data.update()

    # Verify normalized bbox.
    all_co = []
    for o in meshes:
        n = len(o.data.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        o.data.vertices.foreach_get('co', co)
        all_co.append(co.reshape(n, 3))
    co = np.concatenate(all_co, axis=0)
    log("NORM_BBOX", co.min(axis=0), co.max(axis=0), "size", co.max(axis=0) - co.min(axis=0))

    # --- Armature ---
    arm_data = bpy.data.armatures.new("MainCharacterArmature")
    arm = bpy.data.objects.new("mainCharacterRig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    arm.show_in_front = True
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')

    eb = arm_data.edit_bones
    root = eb.new("root")
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 0.30)
    root.use_deform = False

    hips = eb.new("hips")
    hips.head = (0.0, 0.02, 0.90)
    hips.tail = (0.0, 0.02, 1.62)
    hips.parent = root

    head = eb.new("head")
    head.head = (0.0, 0.10, 1.68)
    head.tail = (0.0, 0.10, 3.25)
    head.parent = hips

    leg_l = eb.new("leg.L")
    leg_l.head = (-0.42, 0.06, 0.42)
    leg_l.tail = (-0.42, 0.06, 0.02)
    leg_l.parent = root

    leg_r = eb.new("leg.R")
    leg_r.head = (0.42, 0.06, 0.42)
    leg_r.tail = (0.42, 0.06, 0.02)
    leg_r.parent = root

    bpy.ops.object.mode_set(mode='OBJECT')
    log("BONES", [b.name for b in arm_data.bones])

    # --- Weights (bulk vertex-group assignment, no bmesh: keeps COLOR_0 corner data untouched) ---
    group_names = ['hips', 'head', 'leg.L', 'leg.R']
    BUCKETS = 200

    for oi, o in enumerate(meshes):
        me = o.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(n, 3)

        groups = {name: {} for name in group_names}
        for i in range(n):
            x = float(co[i, 0])
            y = float(co[i, 1])
            z = float(co[i, 2])

            head_w = smoothstep(1.62, 1.95, z)

            z_mask = 1.0 - smoothstep(0.12, 0.55, z)
            x_abs = abs(x)
            x_mask = smoothstep(0.05, 0.22, x_abs) * (1.0 - smoothstep(0.72, 0.95, x_abs))
            y_mask = smoothstep(-0.55, -0.35, y) * (1.0 - smoothstep(0.55, 0.80, y))
            leg_w = min(1.0, z_mask * x_mask * y_mask * 2.0)

            side_l = smoothstep(0.12, -0.12, x)
            leg_l_w = leg_w * side_l
            leg_r_w = leg_w * (1.0 - side_l)

            total_leg = leg_l_w + leg_r_w
            if head_w + total_leg > 1.0:
                s = 1.0 / (head_w + total_leg)
                head_w *= s
                leg_l_w *= s
                leg_r_w *= s
                total_leg = leg_l_w + leg_r_w
            hips_w = max(0.0, 1.0 - head_w - total_leg)

            weights = (
                ('hips', hips_w),
                ('head', head_w),
                ('leg.L', leg_l_w),
                ('leg.R', leg_r_w),
            )
            for name, w in weights:
                if w > 0.001:
                    b = min(BUCKETS - 1, int(w * BUCKETS))
                    groups[name].setdefault(b, []).append(i)

        for name in group_names:
            vg = o.vertex_groups.get(name) or o.vertex_groups.new(name=name)
            for b, inds in groups[name].items():
                vg.add(inds, (b + 0.5) / BUCKETS, 'REPLACE')

        # Ensure the active/render color attribute is COLOR_0.
        if me.color_attributes:
            try:
                me.color_attributes.active_color_index = 0
                me.color_attributes.render_color_index = 0
            except Exception as exc:
                log("COLOR_ATTR_WARN", o.name, exc)

        o.parent = arm
        o.matrix_parent_inverse = Matrix.Identity(4)
        mod = o.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
        mod.use_vertex_groups = True
        log("WEIGHTED", oi, o.name, n, "groups", len(o.vertex_groups))

    # --- Animations ---
    bpy.context.scene.render.fps = FPS
    arm.animation_data_create()

    idle = make_action(arm, "mc_Idle", 90, idle_pose)
    run = make_action(arm, "mc_Run", 24, run_pose)

    ad = arm.animation_data
    ad.action = None
    # Put both actions on their own NLA tracks so ACTIONS mode exports both clips.
    for action in (idle, run):
        track = ad.nla_tracks.new()
        track.name = action.name
        strip = track.strips.new(action.name, 1, action)
        strip.name = action.name
        if hasattr(strip, 'action_slot') and hasattr(action, 'slots') and len(action.slots):
            strip.action_slot = action.slots[0]
        track.mute = False
        log("NLA", track.name, strip.frame_start, strip.frame_end)

    # --- Export ---
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm

    try:
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
        log("SAVED_BLEND", OUT_BLEND)
    except Exception as exc:
        log("SAVE_BLEND_SKIPPED", exc)

    bpy.ops.export_scene.gltf(
        filepath=OUT_GLB,
        export_format='GLB',
        use_selection=True,
        export_apply=False,
        export_yup=True,
        export_animations=True,
        export_animation_mode='ACTIONS',
        export_anim_single_armature=True,
        export_frame_range=False,
        export_force_sampling=True,
        export_optimize_animation_size=True,
        export_skins=True,
        export_def_bones=False,
        export_morph=False,
        export_lights=False,
        export_cameras=False,
        export_vertex_color='ACTIVE',
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=6,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=10,
        export_draco_texcoord_quantization=12,
        export_draco_color_quantization=12,
        export_draco_generic_quantization=12,
    )
    log("EXPORTED", OUT_GLB, os.path.getsize(OUT_GLB))
    log("DONE", time.time() - t0)


main()
