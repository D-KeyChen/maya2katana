#!/usr/bin/python
'''
    maya2katana - Arnold plugin
    Copyright (C) 2016-2018 Andrey Babak, Animagrad

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    Author: Andrey Babak
    e-mail: ababak@gmail.com
    ------------------------------
    Copy shader nodes to Katana
    ------------------------------
'''

import re
import xml.etree.ElementTree as ET

import maya.cmds as cmds

from ... import utils


def replaceTx(key, filepath):
    '''
    Replace all texture paths with their .tx counterparts
    '''
    root, ext = os.path.splitext(filepath)
    if ext:
        ext = '.tx'
    root = root.replace('\\', '/')
    return root + ext


def preprocessSampler(node):
    '''
    We support only some samplerInfo values: facingRation and flippedNormal
    '''
    nodes = {}
    nodeName = node['name']
    connections = {}
    # Check outer connections to find an appropriate Katana replacement node
    nodeConnections = cmds.listConnections(
        nodeName, source=False, destination=True, connections=True, plugs=True)
    if nodeConnections:
        for i in range(len(nodeConnections) / 2):
            connTo = nodeConnections[i * 2]
            connTo = connTo[connTo.find('.') + 1:]
            connFrom = nodeConnections[i * 2 + 1]
            connections[connTo] = {'node': connFrom[:connFrom.find(
                '.')], 'originalPort': connFrom[connFrom.find('.') + 1:]}
    for connectionName in connections:
        if connectionName == 'facingRatio':
            utilityName = utils.uniqueName('facingRatio')
            samplerInfo = {
                'name': utilityName,
                'type': 'facingRatio',
                'attributes': {},
                'connections': {},
                'renamings': {
                    nodeName: {'name': utilityName},
                },
            }
            nodes[utilityName] = samplerInfo
        elif connectionName == 'flippedNormal':
            utilityName = utils.uniqueName('flippedNormal')
            samplerInfo = {
                'name': utilityName,
                'type': 'two_sided',
                'attributes': {
                    'front': [(1.0, 1.0, 1.0, 1.0)],
                    'back': [(0.0, 0.0, 0.0, 1.0)],
                },
                'connections': {},
                'renamings': {
                    nodeName: {'name': utilityName},
                },
            }
            nodes[utilityName] = samplerInfo
    return nodes


def preprocessBump(node):
    '''
    Preprocess bump
    Special processing is done for normal bump
    '''
    nodes = {}
    nodeName = node['name']
    node['weight'] = 10

    attributes = node['attributes']
    # {0: 'bump', 1: 'tangent', 2: 'object'}
    if attributes.get('bumpInterp') == 1:
        node['type'] = 'spaceTransform'
        attributes['type'] = 2  # normal
        attributes['invert_x'] = 0
        attributes['invert_y'] = 0
        attributes['invert_z'] = 0
        attributes['from'] = 4  # tangent
        attributes['to'] = 0  # world
        attributes['color_to_signed'] = 1
        attributes['set_normal'] = 1
    nodes[nodeName] = node
    return nodes


def preprocessRamp(node):
    '''
    Preprocess ramp
    Maya allows several textures to be used instead of colors.
    We support the most common scenario: mixing two textures.
    In this case we replaces ramp with mix node and rampFloat
    '''
    nodes = {}
    nodeName = node['name']

    colorEntryList = {}
    for connectionName, connection in node['connections'].items():
        colorEntryMatch = re.search(r'colorEntryList\[(\d+)\]', connectionName)
        if colorEntryMatch:
            i = int(colorEntryMatch.group(1))
            colorEntryList[i] = connection

    # Get the number of ramp points in Maya
    colorEntryListSize = cmds.getAttr(
        '{node}.colorEntryList'.format(node=nodeName), size=True)
    if colorEntryListSize < 2 and colorEntryList:
        # delete the whole ramp as it does nothing in Katana
        if colorEntryListSize == 1:
            # Get the only dictionary value as we know for sure there is one texture input
            sourceConnection = colorEntryList.values()[0]
            # Here we create a dummy node with no connections,
            # it will be ignored automatically as it's not of known types.
            # But it can be used to perform renames.
            emptyName = utils.uniqueName('Empty')
            emptyNode = {
                'connections': {},
                'renamings': {
                    nodeName: {'name': sourceConnection['node']},
                },
            }
            nodes[emptyName] = emptyNode
        return nodes

    colorEntryListSize = len(colorEntryList)
    if colorEntryListSize > 0 and colorEntryListSize <= 2:
        mixName = utils.uniqueName(nodeName + 'Mix')
        connections = {
            'mix': {'node': nodeName, 'originalPort': None},
        }
        attributes = {}
        colorEntryListIndices = cmds.getAttr(
            nodeName + '.colorEntryList', multiIndices=True)
        i = colorEntryListIndices[0]
        if colorEntryList.get(i):
            connections['input1'] = colorEntryList.get(i)
        else:
            attributes['input1'] = cmds.getAttr('{node}.colorEntryList[{index}].{param}'.format(
                node=nodeName, index=i, param='color'))
        i = colorEntryListIndices[1]
        if colorEntryList.get(i):
            connections['input2'] = colorEntryList.get(i)
        else:
            attributes['input2'] = cmds.getAttr('{node}.colorEntryList[{index}].{param}'.format(
                node=nodeName, index=i, param='color'))
        mix = {
            'name': mixName,
            'type': 'mix',
            'attributes': attributes,
            'connections': connections,
            'renamings': {
                nodeName: {'name': mixName},
            },
        }
        # print 'colorEntryListSize', node, colorEntryListSize
        # print 'colorEntryList', colorEntryList
        # print 'connections', connections
        nodes[mixName] = mix
        node['type'] = 'rampFloat'
    nodes[nodeName] = node
    return nodes


def preprocessNetworkMaterial(node):
    '''
    Preprocess shadingEngine node and remap correct attributes
    '''
    nodes = {}
    nodeName = node['name']
    connections = node['connections']
    newConnections = {}
    for i in ['aiSurfaceShader', 'surfaceShader', 'aiVolumeShader', 'volumeShader']:
        connection = connections.get(i)
        if connection:
            newConnections['arnoldSurface'] = connection
            break
    displacementConnection = connections.get('displacementShader')
    if displacementConnection:
        newConnections['arnoldDisplacement'] = displacementConnection
    nodes[nodeName] = node
    node['connections'] = newConnections
    return nodes


def postprocessNetworkMaterial(node, allNodes):
    '''
    Rename the networkMaterial node and connect bump
    '''
    nodes = {}
    arnoldSurface = node['connections'].get('arnoldSurface')
    if arnoldSurface:
        shaderNode = allNodes.get(arnoldSurface['node'])
        while shaderNode and shaderNode.get('type') in ['aov_write_rgb', 'aov_write_float']:
            passthrough = shaderNode['connections'].get('beauty')
            if passthrough:
                shaderNode = allNodes.get(passthrough.get('node'))
        if shaderNode:
            shaderNodeName = shaderNode['name']
            # Remove the output node to reinsert it back with the new name
            allNodes.pop(shaderNodeName, None)
            materialName = shaderNodeName
            shaderNodeName += '_out'
            shaderNode['name'] = shaderNodeName
            nodes[shaderNodeName] = shaderNode
            node['name'] = materialName
            node['renamings'] = {
                materialName: {'name': shaderNodeName},
            }
            bump = shaderNode['connections'].get('normalCamera')
            if bump:
                node['connections']['arnoldBump'] = bump
                del shaderNode['connections']['normalCamera']
            nodes[materialName] = node
    return nodes


def processNetworkMaterial(xmlGroup, node):
    '''
    Process NetworkMaterial to remove extra input ports
    '''
    for i in ['arnoldSurface', 'arnoldBump', 'arnoldDisplacement']:
        if i not in node['connections']:
            parameter = xmlGroup.find(
                "./port[@name='{param}']".format(param=i))
            xmlGroup.remove(parameter)


def processRamp(xmlGroup, node):
    '''
    Process ramp and rampFloat
    '''
    attributes = node['attributes']
    nodeName = node['name']
    if not nodeName:
        return
    nodeType = node['type']
    if not nodeType:
        return
    connections = node['connections']
    ramp_input = ''
    if str(attributes['type']) == '0':
        ramp_type = 'v'
        ramp_input = attributes.get('vCoord', '0')
        if connections.get('vCoord'):
            ramp_type = 'custom'
            connections['input'] = connections['vCoord']
            del connections['vCoord']
    elif str(attributes['type']) == '1':
        ramp_type = 'u'
        ramp_input = attributes.get('uCoord', '0')
        if connections.get('uCoord'):
            ramp_type = 'custom'
            connections['input'] = connections['uCoord']
            del connections['uCoord']
    elif str(attributes['type']) == '2':
        ramp_type = 'diagonal'
    elif str(attributes['type']) == '3':
        ramp_type = 'radial'
    elif str(attributes['type']) == '4':
        ramp_type = 'circular'
    else:
        utils.log.warning(
            "Can't translate ramp type for node \"{name}\"".format(name=nodeName))
        ramp_type = 'custom'
    keyValue = 'color' if nodeType == 'ramp' else 'value'
    interpolation = 0 if attributes['interpolation'] == 0 else 2
    colorEntryListSize = cmds.getAttr(
        '{node}.colorEntryList'.format(node=nodeName), size=True)
    colorEntryList = []
    hasConnections = False
    colorEntryListIndices = sorted(cmds.getAttr(
        nodeName + '.colorEntryList', multiIndices=True))
    for i in colorEntryListIndices:
        if utils.hasConnection(node, 'colorEntryList[{index}].color'.format(index=i)):
            hasConnections = True
            break
    index = 0
    for i in colorEntryListIndices:
        valuePosition = cmds.getAttr('{node}.colorEntryList[{index}].{param}'.format(
            node=nodeName, index=i, param='position'))
        if hasConnections:
            valueColor = index
            index += 1
        else:
            valueColor = cmds.getAttr('{node}.colorEntryList[{index}].{param}'.format(
                node=nodeName, index=i, param='color'))
            valueColor = valueColor[0]
        colorEntryList.append(
            {keyValue: valueColor, 'position': valuePosition})
    sortedColorEntryList = sorted(colorEntryList, key=lambda x: x['position'])
    for destKey in ['input', 'type', 'position', keyValue, 'interpolation']:
        parameter = xmlGroup.find(
            ".//group_parameter[@name='{param}']".format(param=destKey))
        if parameter is None:
            continue
        enableNode = parameter.find("*[@name='enable']")
        valueNode = parameter.find("*[@name='value']")
        if destKey in ['input', 'type']:
            if not utils.hasConnection(node, destKey):
                enableNode.attrib['value'] = '1'
                if destKey == 'input':
                    value = str(ramp_input)
                elif destKey == 'type':
                    value = ramp_type
                valueNode.attrib['value'] = value
            continue
        enableNode.attrib['value'] = '1'
        tupleSize = int(valueNode.get('tupleSize', '0'))
        valueNode.attrib['size'] = str(tupleSize * colorEntryListSize)
        for i in range(colorEntryListSize):
            if destKey == 'interpolation':
                value = str(interpolation)
            else:
                value = sortedColorEntryList[i][destKey]
            for j in range(tupleSize):
                subValue = ET.SubElement(valueNode, 'number_parameter')
                subValue.attrib['name'] = 'i' + str(i * tupleSize + j)
                subValue.attrib['value'] = str(
                    value[j] if tupleSize > 1 else value)


def preprocessDisplacement(node):
    '''
    Remove the displacement node as there is no counterpart in Katana
    but leave the connections
    '''
    nodes = {}
    nodeName = node['name']
    node['weight'] = 20

    node['type'] = 'range'
    connection = node.get('connections').get('displacement', {})
    rename = connection.get('node')
    node['connections'] = {
        'input': {'node': rename, 'originalPort': utils.getOutConnection(connection)},
    }
    nodes[nodeName] = node
    return nodes


def overrideClampParams(key, value):
    '''
    Maya has an RGB clamp but Katana uses float value so we need to convert
    '''
    if key == 'min':
        value = min(value)
    if key == 'max':
        value = max(value)
    return value


def overrideHairParams(key, value):
    '''
    Special overrides requested by the artists
    '''
    if key == 'dualDepth':
        value = 1
    if key == 'diffuseIndirectStrength':
        value = 1
    if key == 'extraSamplesDiffuse':
        value = 2
    if key == 'extraSamplesGlossy':
        value = 2
    return value


def overrideMaterialParams(key, value):
    '''
    Special overrides requested by the artists
    '''
    if key == 'specular1IndirectClamp' or key == 'specular2IndirectClamp':
        value = 1
    if key == 'specular1Distribution' or key == 'specular2Distribution':
        value = 'ggx'
    return value


# Preprocess keywords:
# - preprocess
# - postprocess (postprocess at level 0)
# - type (override type)
premap = {
    'shadingEngine': {
        'type': 'networkMaterial',
        'preprocess': preprocessNetworkMaterial,
        'postprocess': postprocessNetworkMaterial,
    },
    'displacementShader': {
        'preprocess': preprocessDisplacement,
    },
    'alSurface': {},
    'alLayer': {},
    'alHair': {},
    'aiStandard': {'type': 'standard'},
    'aiVolumeCollector': {'type': 'volume_collector'},
    'aiVolumeSampleFloat': {'type': 'volume_sample_float'},
    'aiVolumeSampleRgb': {'type': 'volume_sample_rgb'},
    'alInputScalar': {},
    'alInputVector': {},
    'luminance': {},
    'aiImage': {'type': 'image'},
    'alCombineColor': {},
    'alCombineFloat': {},
    'alCurvature': {},
    'alJitterColor': {},
    'alLayerColor': {},
    'alLayerFloat': {},
    'alSwitchColor': {},
    'alSwitchFloat': {},
    'alTriplanar': {},
    'alRemapColor': {},
    'alRemapFloat': {},
    'clamp': {},
    'ramp': {'preprocess': preprocessRamp},
    'aiAmbientOcclusion': {'type': 'ambientOcclusion'},
    'bump2d': {'preprocess': preprocessBump},
    'samplerInfo': {'preprocess': preprocessSampler},
    'aiNoise': {'type': 'noise'},
    'alCellNoise': {},
    'alFlake': {},
    'alFlowNoise': {},
    'alFractal': {},
    'aiUserDataFloat': {'type': 'user_data_float'},
    'aiUserDataColor': {'type': 'user_data_rgb'},
    'aiWriteFloat': {'type': 'aov_write_float'},
    'aiWriteColor': {'type': 'aov_write_rgb'},
    'blendColors': {'type': 'mix'},
}

# Mappings keywords:
# - customColor
# - customProcess
mappings = {
    'alSurface': {
        'customColor': (0.2, 0.36, 0.1),
        'diffuseStrength': {
            'diffuseColor': None,
            'diffuseRoughness': None,
            'backlightStrength': {
                'backlightColor': None,
                'backlightIndirectStrength': None,
            },
            'sssMix': {
                'sssMode': ['cubic', 'diffusion', 'directional', 'empirical'],
                'sssDensityScale': None,
                'sssWeight1': {
                    'sssRadius': None,
                    'sssRadiusColor': None,
                },
                'sssWeight2': {
                    'sssRadius2': None,
                    'sssRadiusColor2': None,
                },
                'sssWeight3': {
                    'sssRadius3': None,
                    'sssRadiusColor3': None,
                },
                'sssTraceSet': None,
            },
            'diffuseExtraSamples': None,
            'sssExtraSamples': None,
            'diffuseIndirectStrength': None,
            'diffuseIndirectClamp': None,
            'diffuseNormal': None,
            'traceSetDiffuse': None,
            'traceSetBacklight': None,
        },
        'specular1Strength': {
            'specular1Color': None,
            'specular1Roughness': None,
            'specular1Anisotropy': None,
            'specular1Rotation': None,
            'specular1FresnelMode': ['dielectric', 'metallic'],
            'specular1Ior': None,
            'specular1Reflectivity': None,
            'specular1EdgeTint': None,
            'specular1RoughnessDepthScale': None,
            'specular1ExtraSamples': None,
            'specular1Normal': None,
            'specular1IndirectStrength': None,
            'specular1IndirectClamp': overrideMaterialParams,
            'traceSetSpecular1': None,
            'specular1CausticPaths': None,
            'specular1InternalDirect': None,
            # ['beckmann', 'ggx'],
            'specular1Distribution': overrideMaterialParams,
        },
        'specular2Strength': {
            'specular2Color': None,
            'specular2Roughness': None,
            'specular2Anisotropy': None,
            'specular2Rotation': None,
            'specular2FresnelMode': ['dielectric', 'metallic'],
            'specular2Ior': None,
            'specular2Reflectivity': None,
            'specular2EdgeTint': None,
            'specular2RoughnessDepthScale': None,
            'specular2ExtraSamples': None,
            'specular2Normal': None,
            'specular2IndirectStrength': None,
            'specular2IndirectClamp': overrideMaterialParams,
            'traceSetspecular2': None,
            'specular2CausticPaths': None,
            'specular2InternalDirect': None,
            # ['beckmann', 'ggx']),
            'specular2Distribution': overrideMaterialParams,
        },
        'transmissionStrength': {
            'transmissionColor': None,
            'transmissionLinkToSpecular1': None,
            'transmissionRoughness': None,
            'transmissionIor': None,
            'ssAttenuationColor': None,
            'ssScattering': None,
            'ssDensityScale': None,
            'ssDirection': None,
            'transmissionRoughnessDepthScale': None,
            'transmissionExtraSamples': None,
            'transmissionEnableCaustics': None,
            'rrTransmissionDepth': None,
            'transmissionClamp': None,
            'ssSpecifyCoefficients': None,
            'ssAbsorption': None,
            'traceSetTransmission': None,
            'transmissionDoDirect': None,
            'transmissionNormal': None,
            'transmissionCausticPaths': None,
        },
        'emissionStrength': {
            'emissionColor': None,
        },
        'opacity': None,
    },


    'standard': {
        'customColor': (0.2, 0.36, 0.1),
        'Kd': {
            'color': 'Kd_color',
            'diffuseRoughness': 'diffuse_roughness',
            'Kb': None,
            'directDiffuse': 'direct_diffuse',
            'indirectDiffuse': 'indirect_diffuse',
        },
        'Ks': {
            'KsColor': 'Ks_color',
            'specularRoughness': 'specular_roughness',
            'specularAnisotropy': 'specular_anisotropy',
            'specularDistribution': ('specular_distribution', ['beckmann', 'ggx']),
            'specularRotation': 'specular_rotation',
            'directSpecular': 'direct_specular',
            'indirectSpecular': 'indirect_specular',
            'enableGlossyCaustics': 'enable_glossy_caustics',
        },
        'Kr': {
            'KrColor': 'Kr_color',
            'reflectionExitColor': 'reflection_exit_color',
            'reflectionExitUseEnvironment': 'reflection_exit_use_environment',
            'enableReflectiveCaustics': 'enable_reflective_caustics',
        },
        'Kt': {
            'KtColor': 'Kt_color',
            'transmittance': None,
            'refractionRoughness': 'refraction_roughness',
            'refractionExitColor': 'refraction_exit_color',
            'refractionExitUseEnvironment': 'refraction_exit_use_environment',
            'IOR': None,
            'dispersionAbbe': 'dispersion_abbe',
            'enableRefractiveCaustics': 'enable_refractive_caustics',
            'enableInternalReflections': 'enable_internal_reflections',
        },
        'Fresnel': {
            'Krn': None,
            'specularFresnel': 'specular_Fresnel',
            'Ksn': None,
            'FresnelUseIOR': 'Fresnel_use_IOR',
            'FresnelAffectDiff': 'Fresnel_affect_diff',
        },
        'emission': {
            'emissionColor': 'emission_color',
        },
        'Ksss': {
            'KsssColor': 'Ksss_color',
            'sssProfile': ('sss_profile', ['empirical', 'cubic']),
            'sssRadius': 'sss_radius',
        },
        'bounceFactor': 'bounce_factor',
        'opacity': None,
    },


    'volume_collector': {
        'scatteringSource': ('scattering_source', ['parameter', 'channel']),
        'scatteringChannel': 'scattering_channel',
        'scattering': None,
        'scatteringColor': 'scattering_color',
        'scatteringIntensity': 'scattering_intensity',
        'anisotropy': None,
        'attenuationSource': ('attenuation_source', ['parameter', 'channel', 'scattering']),
        'attenuationChannel': 'attenuation_channel',
        'attenuation': None,
        'attenuationColor': 'attenuation_color',
        'attenuationIntensity': 'attenuation_intensity',
        'attenuationMode': ('attenuation_mode', ['absorption', 'extinction']),
        'emissionSource': ('emission_source', ['parameter', 'channel']),
        'emissionChannel': 'emission_channel',
        'emission': None,
        'emissionColor': 'emission_color',
        'emissionIntensity': 'emission_intensity',
        'positionOffset': 'position_offset',
        'interpolation': ['closest', 'trilinear', 'tricubic'],
    },


    'volume_sample_float': {
        'channel': None,
        'positionOffset': 'position_offset',
        'interpolation': ['closest', 'trilinear', 'tricubic'],
        'inputMin': 'input_min',
        'inputMax': 'input_max',
        'contrast': None,
        'contrastPivot': 'contrast_pivot',
        'bias': None,
        'gain': None,
        'outputMin': 'output_min',
        'outputMax': 'output_max',
        'clampMin': 'clamp_min',
        'clampMax': 'clamp_max',
    },


    'volume_sample_rgb': {
        'channel': None,
        'positionOffset': 'position_offset',
        'interpolation': ['closest', 'trilinear', 'tricubic'],
        'gamma': None,
        'hueShift': 'hue_shift',
        'saturation': None,
        'contrast': None,
        'contrastPivot': 'contrast_pivot',
        'exposure': None,
        'multiply': None,
        'add': None,
    },


    'luminance': {
        'value': 'input',
    },


    'image': {
        'customColor': (0.36, 0.25, 0.38),
        'filename': replaceTx,
        'filter': ['closest', 'bilinear', 'bicubic', 'smart_bicubic'],
        'mipmapBias': 'mipmap_bias',
        'ignoreMissingTiles': ('ignore_missing_tiles', {
            'missingTileColor': 'missing_tile_color',
        }),
        'multiply': None,
        'offset': None,
        'uvset': None,
        'uvcoords': None,
        'soffset': None,
        'toffset': None,
        'swrap': ['periodic', 'black', 'clamp', 'mirror', 'file'],
        'twrap': ['periodic', 'black', 'clamp', 'mirror', 'file'],
        'sscale': None,
        'tscale': None,
        'sflip': None,
        'tflip': None,
        'swapSt': 'swap_st',
    },


    'alCombineColor': {
        'input1': None,
        'input2': None,
        'input3': None,
        'combineOp': [
            'multiply 1*2',
            'add 1+2',
            'divide 1/2',
            'subtract 1-2',
            'lerp(1, 2, 3)',
            'dot(1, 2)',
            'distance(1 -> 2)',
            'cross(1, 2)',
        ],
    },


    'alCombineFloat': {
        'input1': None,
        'input2': None,
        'input3': None,
        'combineOp': [
            'multiply 1*2',
            'add 1+2',
            'divide 1/2',
            'subtract 1-2',
            'lerp(1, 2, 3)',
        ],
    },


    'alInputScalar': {
        'input': ['facing-ratio', 'area', 'face-index', 'ray-length', 'ray-depth', 'User'],
        'userName': None,
        'RMPinputMin': None,
        'RMPinputMax': None,
        'RMPcontrast': None,
        'RMPcontrastPivot': None,
        'RMPbias': None,
        'RMPgain': None,
        'RMPoutputMin': None,
        'RMPoutputMax': None,
        'RMPclampEnable': None,
        'RMPthreshold': None,
        'RMPclampMin': None,
        'RMPclampMax': None,
    },


    'alInputVector': {
        'input': ['P', 'Po', 'N', 'Nf', 'Ng', 'Ngf', 'Ns', 'dPdu',
                  'dPdv', 'Ld', 'Rd', 'uv', 'User', 'Custom'],
        'userName': None,
        'vector': None,
        'type': ['Point', 'Vector'],
        'matrix': None,
        'coordinates': ['cartesian', 'spherical', 'normalized spherical'],
    },


    'alCurvature': {
        'mode': ['positive', 'negative'],
        'samples': None,
        'sampleRadius': None,
        'traceSet': None,
        'RMPinputMin': None,
        'RMPinputMax': None,
        'RMPcontrast': None,
        'RMPcontrastPivot': None,
        'RMPbias': None,
        'RMPgain': None,
        'RMPoutputMin': None,
        'RMPoutputMax': None,
        'RMPclampEnable': None,
        'RMPthreshold': None,
        'RMPclampMin': None,
        'RMPclampMax': None,
        'color1': None,
        'color2': None,
    },


    'alJitterColor': {
        'input': None,
        'minSaturation': None,
        'maxSaturation': None,
        'minGain': None,
        'maxGain': None,
        'minHueOffset': None,
        'maxHueOffset': None,
        'clamp': None,
        'signal': None,
    },


    'alLayerColor': {
        'layer1': None,
        'layer1a': None,
        'layer1blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer2': None,
        'layer2a': None,
        'layer2blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer3': None,
        'layer3a': None,
        'layer3blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer4': None,
        'layer4a': None,
        'layer4blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer5': None,
        'layer5a': None,
        'layer5blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer6': None,
        'layer6a': None,
        'layer6blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer7': None,
        'layer7a': None,
        'layer7blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
        'layer8': None,
        'layer8a': None,
        'layer8blend': [
            'Normal',
            'Lighten',
            'Darken',
            'Multiply',
            'Average',
            'Add',
            'Subtract',
            'Difference',
            'Negation',
            'Exclusion',
            'Screen',
            'Overlay',
            'Soft Light',
            'Hard Light',
            'Color Dodge',
            'Color Burn',
            'Linear Dodge',
            'Linear Burn',
            'Linear Light',
            'Vivid Light',
            'Pin Light',
            'Hard Mix',
            'Reflect',
            'Glow',
            'Phoenix'
        ],
    },


    'alLayerFloat': {
        'layer1': None,
        'layer1a': None,
        'layer2': None,
        'layer2a': None,
        'layer3': None,
        'layer3a': None,
        'layer4': None,
        'layer4a': None,
        'layer5': None,
        'layer5a': None,
        'layer6': None,
        'layer6a': None,
        'layer7': None,
        'layer7a': None,
        'layer8': None,
        'layer8a': None,
    },


    'alSwitchColor': {
        'inputA': None,
        'inputB': None,
        'inputC': None,
        'inputD': None,
        'inputE': None,
        'inputF': None,
        'inputG': None,
        'inputH': None,
        'mix': None,
        'threshold': None,
    },


    'alSwitchFloat': {
        'inputA': None,
        'inputB': None,
        'inputC': None,
        'inputD': None,
        'inputE': None,
        'inputF': None,
        'inputG': None,
        'inputH': None,
        'mix': None,
        'threshold': None,
    },


    'alTriplanar': {
        'customColor': (0.36, 0.25, 0.38),
        'input': None,
        'texture': replaceTx,
        'space': ['world', 'object', 'Pref'],
        'normal': ['geometric', 'smooth', 'smooth-NoBump'],
        'tiling': ['regular', 'cellnoise'],
        'frequency': None,
        'mipMapBias': None,
        'blendSoftness': None,
        'cellSoftness': None,
        'scalex': None,
        'scaley': None,
        'scalez': None,
        'offsetx': None,
        'offsety': None,
        'offsetz': None,
        'rotx': None,
        'roty': None,
        'rotz': None,
        'rotjitterx': None,
        'rotjittery': None,
        'rotjitterz': None,
    },


    'alRemapColor': {
        'input': None,
        'gamma': None,
        'saturation': None,
        'hueOffset': None,
        'contrast': None,
        'contrastPivot': None,
        'gain': None,
        'exposure': None,
        'mask': None,
    },


    'alRemapFloat': {
        'input': None,
        'RMPinputMin': None,
        'RMPinputMax': None,
        'RMPcontrast': None,
        'RMPcontrastPivot': None,
        'RMPbias': None,
        'RMPgain': None,
        'RMPoutputMin': None,
        'RMPoutputMax': None,
        'RMPclampEnable': None,
        'RMPthreshold': None,
        'RMPclampMin': None,
        'RMPclampMax': None,
        'mask': None,
    },


    'alLayer': {
        'customColor': (0.2, 0.56, 0.1),
        'layer1': None,
        'layer2': None,
        'mix': None,
        'debug': ['off', 'layer1', 'layer2', 'mixer'],
    },


    'clamp': {
        'input': None,
        'min': overrideClampParams,
        'max': overrideClampParams,
    },


    'ramp': {
        'customProcess': processRamp,
        #'uCoord': 'input',
        #'vCoord': 'input',
    },


    'rampFloat': {
        'customProcess': processRamp,
        #'uCoord': 'input',
        #'vCoord': 'input',
    },


    'alHair': {
        'customColor': (0.2, 0.36, 0.1),
        'melanin': None,
        'dyeColor': None,
        'specularWidth': None,
        'specularShift': None,
        'opacity': None,
        'randomTangent': None,
        'randomMelanin': None,
        'randomHue': None,
        'randomSaturation': None,
        'glintRolloff': None,
        'transmissionRolloff': None,
        'diffuseStrength': {
            'diffuseColor': None,
            'diffuseScatteringMode': ['kajiya-kay', 'dual-scattering'],
            'diffuseForward': None,
            'diffuseBack': None,
        },
        'specular1Strength': {
            'specular1Color': None,
            'specular1WidthScale': None,
            'specular1Shift': None,
        },
        'specular2Strength': {
            'specular2Color': None,
            'specular2WidthScale': None,
            'specular2Shift': None,
            'glintStrength': None,
        },
        'transmissionStrength': {
            'transmissionColor': None,
            'transmissionWidthScale': None,
            'transmissionShift': None,
        },
        'dualDepth': overrideHairParams,
        'diffuseIndirectStrength': overrideHairParams,
        'extraSamplesDiffuse': overrideHairParams,
        'glossyIndirectStrength': None,
        'extraSamplesGlossy': overrideHairParams,
        'uparam': None,
        'vparam': None,
        'aovDepth': 'aov_depth',
    },


    'ambientOcclusion': {
        'samples': None,
        'spread': None,
        'nearClip': 'near_clip',
        'farClip': 'far_clip',
        'falloff': None,
        'black': None,
        'white': None,
        'opacity': None,
        'invertNormals': 'invert_normals',
        'selfOnly': 'self_only',
    },


    'bump2d': {
        'bumpValue': 'bump_map',
        'bumpDepth': 'bump_height',
    },


    'networkMaterial': {
        'customColor': (0.4, 0.35, 0.2),
        'customProcess': processNetworkMaterial,
    },


    'mix': {
        'input1': None,
        'input2': None,
        'mix': None,
        # Inputs in Maya and Katana are crossed!
        'color1': 'input2',
        'color2': 'input1',
        'blender': 'mix',
    },


    'facingRatio': {
    },


    'two_sided': {
        'front': None,
        'back': None,
    },


    'noise': {
        'octaves': None,
        'distortion': None,
        'lacunarity': None,
        'amplitude': None,
        'scale': None,
        'offset': None,
        'coordSpace': ('coord_space', ['world', 'object', 'Pref']),
    },


    'alCellNoise': {
        'space': ['world', 'object', 'Pref', 'UV'],
        'frequency': None,
        'mode': ['features', 'chips'],
        'randomness': None,
        'octaves': None,
        'lacunarity': None,
        'RMPinputMin': None,
        'RMPinputMax': None,
        'RMPcontrast': None,
        'RMPcontrastPivot': None,
        'RMPbias': None,
        'RMPgain': None,
        'RMPoutputMin': None,
        'RMPoutputMax': None,
        'RMPclampEnable': None,
        'RMPthreshold': None,
        'RMPclampMin': None,
        'RMPclampMax': None,
        'color1': None,
        'color2': None,
        'smoothChips': None,
        'randomChips': None,
        'chipColor1': None,
        'chipProb1': None,
        'chipColor2': None,
        'chipProb2': None,
        'chipColor3': None,
        'chipProb3': None,
        'chipColor4': None,
        'chipProb4': None,
        'chipColor5': None,
        'chipProb5': None,
        'P': None,
    },


    'alFlake': {
        'space': ['tangent', 'world'],
        'amount': None,
        'size': None,
        'divergence': None,
        'P': None,
    },


    'alFlowNoise': {
        'space': ['world', 'object', 'Pref', 'UV'],
        'frequency': None,
        'octaves': None,
        'lacunarity': None,
        'gain': None,
        'angle': None,
        'advection': None,
        'turbulent': None,
        'RMPinputMin': None,
        'RMPinputMax': None,
        'RMPcontrast': None,
        'RMPcontrastPivot': None,
        'RMPbias': None,
        'RMPgain': None,
        'RMPoutputMin': None,
        'RMPoutputMax': None,
        'RMPclampEnable': None,
        'RMPthreshold': None,
        'RMPclampMin': None,
        'RMPclampMax': None,
        'color1': None,
        'color2': None,
        'P': None,
    },


    'alFractal': {
        'mode': ['scalar', 'vector'],
        'space': ['world', 'object', 'Pref', 'UV'],
        'scale': None,
        'frequency': None,
        'time': None,
        'octaves': None,
        'distortion': None,
        'lacunarity': None,
        'gain': None,
        'turbulent': None,
        'RMPinputMin': None,
        'RMPinputMax': None,
        'RMPcontrast': None,
        'RMPcontrastPivot': None,
        'RMPbias': None,
        'RMPgain': None,
        'RMPoutputMin': None,
        'RMPoutputMax': None,
        'RMPclampEnable': None,
        'RMPthreshold': None,
        'RMPclampMin': None,
        'RMPclampMax': None,
        'color1': None,
        'color2': None,
        'P': None,
    },


    'spaceTransform': {
        'bumpValue': 'input',
        'bumpDepth': 'scale',
        'type': ['point', 'vector', 'normal'],
        'order': ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'],
        'invert_x': None,
        'invert_y': None,
        'invert_z': None,
        'color_to_signed': None,
        'from': ['world', 'object', 'camera', 'screen', 'tangent'],
        'to': ['world', 'object', 'camera', 'screen', 'tangent'],
        'tangent': None,
        'set_normal': None,
    },


    'range': {
        'input': None,
        'input_min': None,
        'input_max': None,
        'output_min': None,
        'output_max': None,
        'smoothstep': None,
    },


    'user_data_rgb': {
        'colorAttrName': 'attribute',
        'defaultValue': 'default',
    },


    'user_data_float': {
        'floatAttrName': 'attribute',
        'defaultValue': 'default',
    },


    'aov_write_rgb': {
        'beauty': 'passthrough',
        'input': 'aov_input',
        'aovName': 'aov_name',
        'blend': 'blend_opacity',
    },


    'aov_write_float': {
        'beauty': 'passthrough',
        'input': 'aov_input',
        'aovName': 'aov_name',
    },


}
