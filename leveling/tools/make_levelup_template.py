"""Entfernt "USERNAME" und "ROLLENNAME" aus der Levelup-Vorlage (Inpainting) -> levelup_template.png

Nur nötig, wenn du eine neue Vorlage (mit Beispieltext) einsetzen willst:
    pip install opencv-python-headless
    python leveling/tools/make_levelup_template.py deine_vorlage.png leveling/assets/levelup_template.png

Die Textboxen unten und die Koordinaten oben in leveling/levelup_card.py sind auf 2169 × 725 px
gemessen – bei anderer Größe beides anpassen.
"""
import sys
import cv2
import numpy as np

src, dst = sys.argv[1], sys.argv[2]
img = cv2.imread(src)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

# Textboxen (x0, y0, x1, y1) in der 2169x725-Vorlage
boxes = [
    (908, 322, 1258, 396),   # USERNAME
    (822, 490, 1348, 538),   # ROLLENNAME (im Namensschild)
]

mask = np.zeros_like(gray)
for x0, y0, x1, y1 in boxes:
    region = gray[y0:y1, x0:x1]
    bg = cv2.medianBlur(region, 31)
    # Text = deutlich dunkler als lokaler Hintergrund
    text = ((bg.astype(int) - region.astype(int)) > 18).astype(np.uint8) * 255
    mask[y0:y1, x0:x1] = text

mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
out = cv2.inpaint(img, mask, 9, cv2.INPAINT_TELEA)
# leichtes Weichzeichnen nur in den reparierten Bereichen, damit keine Schlieren bleiben
soft = cv2.GaussianBlur(out, (9, 9), 0)
m3 = cv2.GaussianBlur(mask, (15, 15), 0)[..., None] / 255.0
out = (out * (1 - m3) + soft * m3).astype(np.uint8)
cv2.imwrite(dst, out)
