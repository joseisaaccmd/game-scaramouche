import * as THREE from 'three'

// The display grade (saturation / warmth / brightness) runs in the final post pass, AFTER the
// character is already drawn into the scene buffer. For the old flat-coloured hero that was fine:
// its palette was authored inside the grade. The plush's COLOR_0 is authored as its own artwork, so
// the night grade desaturates/warms it into beige. These shared uniforms carry the inverse of the
// active grade into the vertex-coloured character material, cancelling the grade for the plush only.
export const heroGradeUniforms = {
    uHeroGradeInverse: { value: new THREE.Matrix3() },
    uHeroGradeInverseOld: { value: new THREE.Matrix3() },
    uHeroGradeEnabled: { value: 0 },
}

// Row-major grade matrix A, matching the SharpenPass shader:
//   color *= brightness
//   color  = mix(vec3(luma), color, saturation)
//   color *= vec3(1 + warmth, 1, 1 - warmth)
const LR = 0.2126
const LG = 0.7152
const LB = 0.0722

export function buildGradeMatrix(grade, target = new THREE.Matrix3()) {
    const saturation = grade?.saturation ?? 1
    const warmth = grade?.warmth ?? 0
    const brightness = grade?.brightness ?? 1
    const s = saturation
    const t = 1 - saturation
    const wr = (1 + warmth) * brightness
    const wg = brightness
    const wb = (1 - warmth) * brightness

    return target.set(
        wr * (s + t * LR), wr * (t * LG), wr * (t * LB),
        wg * (t * LR), wg * (s + t * LG), wg * (t * LB),
        wb * (t * LR), wb * (t * LG), wb * (s + t * LB),
    )
}

export function setHeroGrade(grade, oldGrade = grade) {
    buildGradeMatrix(grade, heroGradeUniforms.uHeroGradeInverse.value).invert()
    buildGradeMatrix(oldGrade, heroGradeUniforms.uHeroGradeInverseOld.value).invert()
}
