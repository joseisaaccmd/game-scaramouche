uniform vec3 uBaseColor;
// Outgoing theme's base colour (masked theme transitions) — the hero / sheep recolour sweeps with
// the portal edge like the world instead of snapping at the click.
uniform vec3 uBaseColorOld;
uniform int uDebugMode;
uniform int uPainterlyEnabled;
uniform sampler2D uPainterlyTexture;
uniform float uPainterlyScale;
uniform float uPainterlyContrast;
uniform float uPainterlyBrightnessVariation;
// Reveal-edge fade (companions only; the hero leaves uFade = 0 so this is a no-op for it).
uniform float uFade;
uniform vec3 uBackgroundColor;
// Optional base-colour texture (mask faces), gated by uUseBaseTexture; flat uBaseColor otherwise.
uniform sampler2D uBaseTexture;
uniform int uUseBaseTexture;
// Baked vertex colour (COLOR_0). The plush hero sets this to 1 so the painted face / outfit show
// through; everything else leaves it 0 and keeps the flat uBaseColor.
uniform float uUseVertexColor;

// Inverse of the active display grade (PainterlyPostProcessing writes these every frame). The plush
// is drawn into the scene buffer before the grade runs, so pre-inverting the grade lets its authored
// palette survive the night/day grade unchanged.
uniform mat3 uHeroGradeInverse;
uniform mat3 uHeroGradeInverseOld;
uniform float uHeroGradeEnabled;

// In-shader cartoon eyes (head mesh only, uDrawEyes = 1) — drawn in the second UV set (uv1), where
// the front face is laid out. CharacterEyes pushes the blink / glance / shape params in each frame.
uniform int uDrawEyes;
uniform vec3 uEyeColor;
uniform vec3 uPupilColor;
uniform float uEyeRadius;
uniform float uEyeSpacing;
uniform float uEyeOffsetY;
uniform float uEyeAspect;
uniform float uEyeNoiseScale;
uniform float uEyeNoiseStrength;
uniform float uPupilWidth;
uniform float uPupilHeight;
uniform float uPupilOffsetX;
uniform float uPupilOffsetY;
uniform float uPupilNoiseScale;
uniform float uPupilNoiseStrength;
uniform float uEyeEdgeSoftness;
uniform float uEyeBlink;

#include ../includes/themeMask.glsl

varying vec3 vObjectPosition;
varying vec3 vObjectNormal;
varying vec3 vInstanceTint; // per-instance colour jitter (sheep scales); vec3(1) everywhere else
varying vec3 vVertexColor; // baked COLOR_0; enabled only for the plush hero
varying vec2 vUv1;
varying vec2 vUv; // first UV set (TEXCOORD_0) — used only when uUseBaseTexture (mask face texture)

// Stable per-pixel dither (interleaved gradient noise) for the reveal-edge dissolve.
float ditherNoise(vec2 p) {
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

// The game's post chain renders the scene into a linear target and writes that buffer to the sRGB
// canvas without a final conversion. Baked COLOR_0 is linear, so a vertex-coloured character must
// encode it here or its mid-tones display as near-black (the plush's lavender hood turns navy).
vec3 heroSRGBEncode(vec3 value) {
    return mix(pow(value, vec3(0.41666)) * 1.055 - vec3(0.055), value * 12.92, vec3(lessThanEqual(value, vec3(0.0031308))));
}

float samplePainterlyTexture(vec3 position, vec3 normalDirection) {
    vec3 blendWeights = pow(abs(normalDirection), vec3(4.0));
    blendWeights /= max(blendWeights.x + blendWeights.y + blendWeights.z, 0.0001);

    float xProjection = texture2D(uPainterlyTexture, position.yz).r;
    float yProjection = texture2D(uPainterlyTexture, position.xz).r;
    float zProjection = texture2D(uPainterlyTexture, position.xy).r;

    return xProjection * blendWeights.x + yProjection * blendWeights.y + zProjection * blendWeights.z;
}

#include ../includes/simplexNoise2d.glsl

// Composite the two eyes (+ squished pupils + blink) onto the head colour, sampled in uv1.
vec3 drawEyes(vec3 baseColor, vec2 uv1) {
    vec2 euv = uv1 - 0.5;
    float side = euv.x < 0.0 ? -1.0 : 1.0;
    vec2 ep = euv - vec2(side * uEyeSpacing * 0.5, uEyeOffsetY);

    vec2 epe = ep / vec2(max(uEyeRadius * uEyeAspect, 1e-3), max(uEyeRadius, 1e-3));
    float er = length(epe);
    float eedge = 1.0 + snoise(epe * uEyeNoiseScale) * uEyeNoiseStrength;
    float emask = 1.0 - smoothstep(eedge - uEyeEdgeSoftness, eedge, er);

    float ap = (1.0 - uEyeBlink) * uEyeRadius;
    float lidS = max(uEyeRadius * uEyeEdgeSoftness, 1e-4);
    emask *= 1.0 - smoothstep(ap - lidS, ap, abs(ep.y));

    vec2 epp = (ep - vec2(uPupilOffsetX, uPupilOffsetY)) / vec2(max(uPupilWidth, 1e-3), max(uPupilHeight, 1e-3));
    float erp = length(epp);
    float pedge = 1.0 + snoise(epp * uPupilNoiseScale + 11.3) * uPupilNoiseStrength;
    float pmask = 1.0 - smoothstep(pedge - uEyeEdgeSoftness, pedge, erp);

    return mix(baseColor, mix(uEyeColor, uPupilColor, pmask), emask);
}

void main() {
    float painterlyValue = 0.5;
    vec3 baseColor = mix(uBaseColorOld, uBaseColor, themeMaskNewness());
    if (uUseBaseTexture == 1) {
        baseColor = texture2D(uBaseTexture, vUv).rgb;
    }
    vec3 finalColor = baseColor * vInstanceTint * mix(vec3(1.0), vVertexColor, uUseVertexColor);
    if (uPainterlyEnabled == 1) {
        painterlyValue = samplePainterlyTexture(vObjectPosition * uPainterlyScale, normalize(vObjectNormal));
        painterlyValue = clamp((painterlyValue - 0.5) * uPainterlyContrast + 0.5, 0.0, 1.0);
        float signedVariation = painterlyValue * 2.0 - 1.0;
        finalColor *= 1.0 + signedVariation * uPainterlyBrightnessVariation;
    }

    if (uDebugMode == 1) {
        finalColor = uBaseColor;
    } else if (uDebugMode == 2) {
        finalColor = vec3(painterlyValue);
    }

    // In-shader eyes (head mesh only) — drawn last so they read on top of the head paint.
    if (uDrawEyes == 1) {
        finalColor = drawEyes(finalColor, vUv1);
    }

    // Reveal-edge fade (uFade 0→1): a SCREEN-DOOR dither dissolve (not alpha) so the creature stays
    // OPAQUE and depth-sorts cleanly with the transparent grass — instead of blending through it and
    // ghosting. A small colour pull toward the background softens the dissolving pixels.
    if (uFade > 0.0) {
        finalColor = mix(finalColor, uBackgroundColor, uFade * 0.5);
        if (uFade >= ditherNoise(gl_FragCoord.xy)) discard;
    }
    gl_FragColor = vec4(clamp(finalColor, 0.0, 1.0), 1.0);

    if (uUseVertexColor > 0.5) {
        vec3 encoded = heroSRGBEncode(gl_FragColor.rgb);
        if (uHeroGradeEnabled > 0.5) {
            // Cancel the post pass's display grade for the plush only. The inverse can ask for
            // channels above 1 (the night grade is a strong desaturation); clamp and scale the
            // whole colour evenly instead of letting an LDR buffer clip one channel, which would
            // turn the lavender hood grey. Losing a little brightness keeps the hue.
            vec3 compensated = mix(uHeroGradeInverseOld * encoded, uHeroGradeInverse * encoded, themeMaskNewness());
            compensated = max(compensated, 0.0);
            float peak = max(compensated.r, max(compensated.g, compensated.b));
            gl_FragColor.rgb = compensated / max(1.0, peak);
        } else {
            gl_FragColor.rgb = encoded;
        }
    } else {
        #include <colorspace_fragment>
    }
}
