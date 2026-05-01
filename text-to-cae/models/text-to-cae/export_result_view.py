"""Export an Abaqus viewport image for the completed Text-to-CAE ODB."""

from __future__ import print_function

import os

from abaqus import session
from abaqusConstants import CONTOURS_ON_DEF, PNG
from odbAccess import openOdb
import visualization


def script_root():
    env_root = os.environ.get("TEXT_TO_CAE_ROOT", "")
    if env_root:
        return os.path.abspath(env_root)
    script_path = globals().get("__file__", "")
    if script_path:
        return os.path.dirname(os.path.abspath(script_path))
    return os.getcwd()


ROOT = script_root()
ODB_PATH = os.path.join(ROOT, "TextToCAE_Cantilever.odb")
OUT_BASE = os.path.join(ROOT, "TextToCAE_Cantilever_result")


def main():
    odb = openOdb(path=ODB_PATH, readOnly=True)
    viewport = session.Viewport(name="Text-to-CAE Result", origin=(0, 0), width=240, height=150)
    viewport.setValues(displayedObject=odb)
    viewport.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    viewport.odbDisplay.setPrimaryVariable(
        variableLabel="S",
        outputPosition=visualization.INTEGRATION_POINT,
        refinement=(visualization.INVARIANT, "Mises"),
    )
    viewport.view.fitView()
    session.printOptions.setValues(vpDecorations=True, vpBackground=False)
    session.pngOptions.setValues(imageSize=(1600, 1000))
    session.printToFile(fileName=OUT_BASE, format=PNG, canvasObjects=(viewport,))
    odb.close()
    print("Exported {}".format(OUT_BASE + ".png"))


if __name__ == "__main__":
    main()
