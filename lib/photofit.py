#!/usr/bin/env python3
"""photofit: phone photo of an object on the Calibration Mat -> exact outline in mm -> custom-fit Gridfinity bin / tray.

    forge photofit mat                       # writes out/photofit/calibration_mat_letter.pdf (print at 100% / "Actual size")
    forge photofit photo.jpg [--depth 15] [--bin auto|NxM] [--name thing]
How: 4 ArUco markers at known spots -> homography -> top-down image at 8 px/mm -> object = what isn't paper
(colour distance + darkness, shadows suppressed) -> biggest blob inside the work area -> contour in mm -> pocket.
Accuracy ~0.3-0.6 mm for flat objects shot from straight above (>= 35 cm away). Tall objects: the photo sees the TOP
outline slightly bigger (parallax) -> photofit uses the bottom-most outline it can see + the loose_fit gap.
Check the print: the 100 mm bar on the mat must measure 100 mm (if not: --scale-fix 100/<measured>).
"""
import argparse, json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FORGE = os.path.dirname(HERE)
OUT = os.path.join(FORGE, "out", "photofit")

PAGE = (215.9, 279.4)              # US Letter, mm
MK = 28.0                          # marker side, mm
MARGIN = 14.0
CENTERS = {0: (MARGIN + MK / 2, MARGIN + MK / 2), 1: (PAGE[0] - MARGIN - MK / 2, MARGIN + MK / 2),
           2: (PAGE[0] - MARGIN - MK / 2, PAGE[1] - MARGIN - MK / 2), 3: (MARGIN + MK / 2, PAGE[1] - MARGIN - MK / 2)}
DICT = None


def aruco():
    import cv2
    global DICT
    DICT = DICT or cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return DICT


def marker_corners_mm(i):
    cx, cy = CENTERS[i]; h = MK / 2
    return np.array([(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)], np.float32)   # TL TR BR BL (y down)


def make_mat(dpi=300):
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    px = lambda mm: int(round(mm / 25.4 * dpi))
    W, H = px(PAGE[0]), px(PAGE[1])
    im = Image.new("L", (W, H), 255); d = ImageDraw.Draw(im)
    for i in CENTERS:
        m = cv2.aruco.generateImageMarker(aruco(), i, px(MK))
        tl = marker_corners_mm(i)[0]
        im.paste(Image.fromarray(m), (px(tl[0]), px(tl[1])))
    x0, y0 = MARGIN + MK + 6, MARGIN + 4
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", px(5))
        fs = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", px(3))
    except Exception:
        f = fs = ImageFont.load_default()
    d.text((px(x0), px(y0)), "MAX MAT  -  print at 100% (Actual size)", fill=0, font=f)
    d.text((px(x0), px(y0 + 8)), "object in the middle, phone straight above, no flash", fill=0, font=fs)
    # 100 mm scale bar + 50 mm check square (bottom middle)
    by = PAGE[1] - MARGIN - 10
    bx = PAGE[0] / 2 - 50
    d.rectangle([px(bx), px(by), px(bx + 100), px(by + 1.2)], fill=0)
    for k in range(11):
        d.rectangle([px(bx + 10 * k) - 2, px(by - 2.5), px(bx + 10 * k) + 2, px(by + 1.2)], fill=0)
    d.text((px(bx), px(by + 2.5)), "this bar = 100 mm", fill=0, font=fs)
    # light work-area frame
    wa = (MARGIN, MARGIN + MK + 4, PAGE[0] - MARGIN, PAGE[1] - MARGIN - MK - 4)
    for k in range(0, int(wa[2] - wa[0]), 4):
        d.line([px(wa[0] + k), px(wa[1]), px(wa[0] + k + 2), px(wa[1])], fill=170, width=2)
        d.line([px(wa[0] + k), px(wa[3]), px(wa[0] + k + 2), px(wa[3])], fill=170, width=2)
    os.makedirs(OUT, exist_ok=True)
    pdf = os.path.join(OUT, "calibration_mat_letter.pdf"); png = os.path.join(OUT, "calibration_mat_letter.png")
    im.save(png); im.convert("RGB").save(pdf, resolution=dpi)
    return pdf, png


def rectify(img_bgr, ppm=8.0):
    import cv2
    det = cv2.aruco.ArucoDetector(aruco(), cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(img_bgr)
    if ids is None or len(ids) < 3:
        raise SystemExit(f"found {0 if ids is None else len(ids)} of 4 mat markers: retake the photo (whole mat in view, sharp)")
    src, dst = [], []
    for c, i in zip(corners, ids.ravel()):
        if int(i) in CENTERS:
            src.append(c.reshape(4, 2)); dst.append(marker_corners_mm(int(i)) * ppm)
    src, dst = np.concatenate(src), np.concatenate(dst)
    Hm, _ = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    reproj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), Hm).reshape(-1, 2)
    err_mm = float(np.sqrt(((reproj - dst) ** 2).sum(1)).mean() / ppm)
    top = cv2.warpPerspective(img_bgr, Hm, (int(PAGE[0] * ppm), int(PAGE[1] * ppm)), flags=cv2.INTER_CUBIC,
                              borderValue=(255, 255, 255))
    return top, len(src) // 4, err_mm


def segment(top, ppm=8.0):
    import cv2
    lab = cv2.cvtColor(top, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    # paper reference = median of the work area; shadows: darker but NOT coloured -> need a bigger L drop
    wa = (int((MARGIN + 2) * ppm), int((MARGIN + MK + 6) * ppm), int((PAGE[0] - MARGIN - 2) * ppm), int((PAGE[1] - MARGIN - MK - 6) * ppm))
    roi = (slice(wa[1], wa[3]), slice(wa[0], wa[2]))
    Lp = np.median(L[roi]); Ap = np.median(A[roi]); Bp = np.median(B[roi])
    chroma = np.sqrt((A - Ap) ** 2 + (B - Bp) ** 2)
    dark = Lp - L
    fg = (chroma > 14) | (dark > 55)
    # local paper level (handles uneven light): compare to a big blur of the image
    bl = cv2.GaussianBlur(L, (0, 0), 25 * ppm / 8)
    fg |= (bl - L) > 40
    m = np.zeros_like(fg); m[roi] = fg[roi]
    k = np.ones((3, 3), np.uint8)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k, iterations=2)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k, iterations=4)
    n, lab_, stats, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        raise SystemExit("no object found on the mat (is it the same colour as the paper? put it on a contrasting sheet)")
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    obj = (lab_ == big).astype(np.uint8)
    from scipy import ndimage
    obj = ndimage.binary_fill_holes(obj).astype(np.uint8)
    cs, _ = cv2.findContours(obj, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, 0.25 * ppm, True).reshape(-1, 2).astype(float)   # 0.25 mm simplification
    mm = c / ppm
    mm[:, 1] = -mm[:, 1]                                                      # image y-down -> CAD y-up
    ctr = (mm.max(0) + mm.min(0)) / 2
    return (mm - ctr), obj


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo"); ap.add_argument("--depth", type=float, default=12.0)
    ap.add_argument("--bin", default="auto"); ap.add_argument("--name"); ap.add_argument("--scale-fix", type=float, default=1.0)
    ap.add_argument("--no-bin", action="store_true")
    a = ap.parse_args()
    if a.photo == "mat":
        pdf, png = make_mat(); print(json.dumps({"pdf": pdf, "png": png})); return
    import cv2
    img = cv2.imread(a.photo)
    if img is None:
        raise SystemExit("can't read photo " + a.photo)
    top, nmk, err = rectify(img)
    outline, mask = segment(top)
    outline *= a.scale_fix
    name = a.name or os.path.splitext(os.path.basename(a.photo))[0]
    od = os.path.join(OUT, name); os.makedirs(od, exist_ok=True)
    cv2.imwrite(os.path.join(od, "rectified.jpg"), top)
    w, h = outline.max(0) - outline.min(0)
    area = 0.5 * abs(np.sum(outline[:, 0] * np.roll(outline[:, 1], -1) - np.roll(outline[:, 0], -1) * outline[:, 1]))
    res = {"name": name, "markers": nmk, "homography_err_mm": round(err, 3), "size_mm": [round(float(w), 2), round(float(h), 2)],
           "area_mm2": round(float(area), 1), "points": len(outline), "depth": a.depth,
           "outline_mm": [[round(float(x), 3), round(float(y), 3)] for x, y in outline]}
    json.dump(res, open(os.path.join(od, "outline.json"), "w"), indent=1)
    if not a.no_bin:
        sys.path.insert(0, HERE)
        import gridfinity as gf
        from build123d import export_stl
        import fit
        g = fit.get("loose_fit")
        if a.bin == "auto":
            nx = max(1, math.ceil((w + 2 * g + 2 * 3.0 + 2 * gf.WALL) / gf.GRID)); ny = max(1, math.ceil((h + 2 * g + 2 * 3.0 + 2 * gf.WALL) / gf.GRID))
        else:
            nx, ny = map(int, a.bin.lower().split("x"))
        nz = max(2, math.ceil((a.depth + gf.FLOOR_TOP + 2.0) / gf.HU))
        s = gf.bin_(nx, ny, nz, magnets=False, cutout=res, depth=a.depth)
        stl = os.path.join(od, f"{name}_bin_{nx}x{ny}x{nz}.stl")
        export_stl(s, stl, tolerance=0.01, angular_tolerance=0.1)
        res["bin"] = stl; res["bin_units"] = [nx, ny, nz]
    print(json.dumps({k: v for k, v in res.items() if k != "outline_mm"}))


if __name__ == "__main__":
    main()
