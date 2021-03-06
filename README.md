# maya2katana

Easily copy shading nodes from [Maya](http://www.autodesk.com/products/maya/overview) to [Katana](https://www.foundry.com/products/katana)

### Currently supported renderers:

- #### [Arnold 5](https://www.arnoldrenderer.com/arnold/) (bate)
   Supported nodes: aiStandardSurface, aiStandardHair, aiNormalMap, aiColorCorrect, 
   aiBump2d, aiImage, aiMultiply, aiDivide, aiPow, aiLayerShader,  aiSpaceTransform, 
   aiClamp, 
   file, ramp, bump2d, multiplyDivide, blendColors, clamp
<!-- 
- #### [RenderMan 21.7+](https://renderman.pixar.com/)
  Supported nodes: aaOceanPrmanShader, PxrAdjustNormal, PxrAovLight, PxrAttribute,
  PxrBackgroundDisplayFilter, PxrBackgroundSampleFilter, PxrBakePointCloud, PxrBakeTexture,
  PxrBarnLightFilter, PxrBlack, PxrBlackBody, PxrBlend, PxrBlockerLightFilter, PxrBump,
  PxrBumpManifold2D, PxrCamera, PxrChecker, PxrClamp, PxrColorCorrect, PxrCombinerLightFilter,
  PxrConstant, PxrCookieLightFilter, PxrCopyAOVDisplayFilter, PxrCopyAOVSampleFilter, PxrCross,
  PxrCryptomatte, PxrCurvature, PxrDebugShadingContext, PxrDefault, PxrDiffuse, PxrDirectLighting,
  PxrDirt, PxrDiskLight, PxrDisney, PxrDisplace, PxrDispScalarLayer, PxrDispTransform, PxrDispVectorLayer,
  PxrDisplayFilterCombiner, PxrDistantLight, PxrDomeLight, PxrDot, PxrEdgeDetect, PxrEnvDayLight,
  PxrExposure, PxrFacingRatio, PxrFilmicTonemapperDisplayFilter, PxrFilmicTonemapperSampleFilter,
  PxrFlakes, PxrFractal, PxrFractalize, PxrGamma, PxrGeometricAOVs, PxrGlass, PxrGoboLightFilter,
  PxrGradeDisplayFilter, PxrGradeSampleFilter, PxrHSL, PxrHair, PxrHairColor,
  PxrHalfBufferErrorFilter, PxrImageDisplayFilter, PxrImagePlaneFilter, PxrIntMultLightFilter,
  PxrInvert, PxrLMDiffuse, PxrLMGlass, PxrLMLayer, PxrLMMetal, PxrLMMixer, PxrLMPlastic,
  PxrLMSubsurface, PxrLayer, PxrLayerMixer, PxrLayerSurface, PxrLayeredBlend, PxrLayeredTexture,
  PxrLightEmission, PxrLightProbe, PxrLightSaturation, PxrManifold2D, PxrManifold3D,
  PxrManifold3DN, PxrMarschnerHair, PxrMatteID, PxrMeshLight, PxrMix, PxrMultiTexture,
  PxrNormalMap, PxrOcclusion, PxrPathTracer, PxrPortalLight, PxrPrimvar, PxrProjectionLayer,
  PxrProjectionStack, PxrProjector, PxrPtexture, PxrRamp, PxrRampLightFilter,
  PxrRandomTextureManifold, PxrRectLight, PxrRemap, PxrRodLightFilter, PxrRollingShutter,
  PxrRoundCube, PxrSeExpr, PxrShadedSide, PxrShadowDisplayFilter, PxrShadowFilter, PxrSkin,
  PxrSphereLight, PxrSurface, PxrTangentField, PxrTee, PxrTexture, PxrThinFilm, PxrThreshold,
  PxrTileManifold, PxrToFloat, PxrToFloat3, PxrVariable, PxrVary, PxrVolume, PxrVoronoise,
  PxrWhitePointDisplayFilter, PxrWhitePointSampleFilter, PxrWorley -->

### Installation

1. Quit Maya

2. Clone maya2katana repository (or download zip, extract and rename directory from "maya2katana-master" to "maya2katana") and place it to:
```
Windows: \Users\<username>\Documents\maya\scripts
Linux: ~/maya/scripts
```

3. Open Script Editor and paste the following code to Python tab:
```python
import maya2katana
reload (maya2katana)
maya2katana.copy()
```

4. To create a shelf button select the code and middle-mouse-drag it to your shelf

### Usage

1. Select a shading network or a single shadingEngine (Shading Group) node
![Maya shading network](doc/maya.jpg)

2. Press the button you've created earlier or execute a script (see installation step)

3. Switch to Katana and paste the nodes
![Resulting Katana shading network](doc/katana.jpg)

### Integrations

To get the XML from shading network name:
```python
import maya2katana
reload (maya2katana)
node_name = 'materialSG'
# Get the xml as string
resulting_xml = maya2katana.generate_xml(node_name)
```

You can save the resulting XML to file and bring it into Katana:

```python
# Now create the Katana shading network
# Suppose the XML (string) is already loaded
# to 'resulting_xml' string variable
from Katana import NodegraphAPI, KatanaFile
# Create a group for shading network
group_name = 'materialSG'
group_node = NodegraphAPI.CreateNode(group_name, NodegraphAPI.GetRootNode())
# Bring the nodes to Katana scene
# and place them inside the newly created group
nodes = KatanaFile.Paste(resulting_xml, group_node)
```

----

## Arnold 5 escription
### Incompatible with "Arnold 4" (与"Arnold 4"不兼容)
### May be incompatible with "RenderMan" (可能与"RenderMan"不兼容)
### Using Maya node requires setting up the renderer (使用Maya节点需要设置渲染器)
Description currently: (当前说明)
 1. The texture path will be converted to a ".tx" path (纹理路径将转换为".tx"路径)
 2. Maya File to aiImage (Maya文件转为aiImage)
    Supported attributes (支持的属性): Image Name, Color Space, Color Gain, Color Offset
 3. aiImage add Color Space support
 4. Maya Ramp to Arnold Ramp_RGB (Maya渐变转为阿诺德渐变)
 5. Maya BlendColors to Arnold Mix_RGBA (Maya颜色混合转为阿诺德混合颜色)

<!-- Currently existing problems: (当前存在的问题) -->
 <!-- - Does not convert image format to .TX (不将图像格式转换为 .TX) -->

