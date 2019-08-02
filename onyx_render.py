#!/usr/bin/env python3

import tempfile
from zipfile import ZipFile
import sqlite3
import os
import json
from fpdf import FPDF
import numpy as np
from tqdm import tqdm
import sys

def get_dir(dirs, parent):
    dlist = []
    while parent is not None:
        p = dirs[parent]
        parent = p["parent"]
        dlist.insert(0, p["title"])

    return os.path.join(*dlist) if dlist else ""

def read_doc_list(tmpdir):
    res = []

    conn = sqlite3.connect(os.path.join(tmpdir, "ShapeDatabase.db"))
    c = conn.cursor()
    c.execute('select uniqueId,title,parentUniqueId from NoteModel where type = 0')
    dirs = {}
    for row in c:
        id, title, parent = row
        dirs[id] = {"title": title, "parent": parent}

    c = conn.cursor()
    c.execute('select uniqueId,title,pageNameList,parentUniqueId from NoteModel where type = 1')
    for row in c:
        id, title, namelist, parent = row
        namelist = json.loads(namelist)["pageNameList"]

        res.append({"id": id, "title": title, "pages": namelist,
                    "dirname": get_dir(dirs, parent)})

    return res

def render_pdf(descriptor, tmpdir):
    pdf = FPDF(orientation='P', unit='mm', format='letter')
    scale = 279
    width_scale = 0.1

    conn = sqlite3.connect(os.path.join(tmpdir, descriptor["id"] + ".db"))

    print("Rendering note %s" % descriptor["title"])
    for page in tqdm(descriptor["pages"]):
        pdf.add_page()

        c = conn.cursor()
        c.execute('select points, matrixValues, thickness from NewShapeModel where pageUniqueId = "'+page+'"')

        for i, row in enumerate(c):
            # Read / parse DB entries
            points, matrix, thickness = row
            matrix = np.asarray(json.loads(matrix)["values"], dtype=np.float32).reshape(3,3)

            d = np.frombuffer(points, dtype=np.float32)
            d = d.byteswap()

            d = d.reshape(-1, 6)

            # Projection matrix
            points = d[:, :2]
            points = np.concatenate((points, np.ones([points.shape[0],1])), axis=1)
            points = points @ matrix.T
            points = points[:, :2]

            # Draw
            pdf.set_line_width(thickness * width_scale)

            points = points * scale

            for r in range(points.shape[0] - 1):
                x_start = points[r][0]
                y_start = points[r][1]

                x_end = points[r + 1][0]
                y_end = points[r + 1][1]

                pdf.line(x_start, y_start, x_end, y_end)
    return pdf

def render_all(zip_name, save_to):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract note backup file
        with ZipFile(zip_name, 'r') as zipObj:
            zipObj.extractall(tmpdir)

        notes = read_doc_list(tmpdir)
        print("Found note structure:")
        for note in notes:
            print("   ", os.path.join(note["dirname"], note["title"]))

        for note in notes:
            pdf = render_pdf(note, tmpdir)
            dir = os.path.join(save_to, note["dirname"])
            os.makedirs(dir, exist_ok=True)

            pdf.output(os.path.join(dir, "%s.pdf" % note["title"]))

if __name__ == "__main__":
    if len(sys.argv)!=3:
        print("Usage: %s <note backup file> <dir to render>" % sys.argv[0])
        sys.exit(-1)

    zip_name = sys.argv[1]
    save_to = sys.argv[2]

    render_all(zip_name, save_to)