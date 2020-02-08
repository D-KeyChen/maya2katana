#!/usr/bin/python
"""
    maya2katana - Arnold plugin
    Copyright (C) 2016-2019 Andriy Babak, Animagrad

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

    Author: Andriy Babak
    e-mail: ababak@gmail.com
    ------------------------------
    Copy shader nodes to Katana
    ------------------------------
"""

import re
import os

import maya.cmds as cmds

from ... import utils, ET


def replace_tx(key, filepath):
    """
    Replace all texture paths with their .tx counterparts
    """
    root, ext = os.path.splitext(filepath)
    if ext:
        ext = ".tx"
    root = root.replace("\\", "/")
    return root + ext


def preprocess_sampler(node):
    """
    We support only some samplerInfo values: facingRation and flippedNormal
    """
    nodes = {}
    node_name = node["name"]
    connections = {}
    # Check outer connections to find an appropriate Katana replacement node
    node_connections = cmds.listConnections(
        node_name, source=False, destination=True, connections=True, plugs=True
    )
    if node_connections:
        for i in range(len(node_connections) / 2):
            conn_to = node_connections[i * 2]
            conn_to = conn_to[conn_to.find(".") + 1 :]
            conn_from = node_connections[i * 2 + 1]
            connections[conn_to] = {
                "node": conn_from[: conn_from.find(".")],
                "original_port": conn_from[conn_from.find(".") + 1 :],
            }
    for connection_name in connections:
        if connection_name == "facingRatio":
            utility_name = utils.unique_name("facingRatio")
            sampler_info = {
                "name": utility_name,
                "type": "facingRatio",
                "attributes": {},
                "connections": {},
                "renamings": {node_name: {"name": utility_name},},
            }
            nodes[utility_name] = sampler_info
        elif connection_name == "flippedNormal":
            utility_name = utils.unique_name("flippedNormal")
            sampler_info = {
                "name": utility_name,
                "type": "two_sided",
                "attributes": {
                    "front": [(1.0, 1.0, 1.0, 1.0)],
                    "back": [(0.0, 0.0, 0.0, 1.0)],
                },
                "connections": {},
                "renamings": {node_name: {"name": utility_name},},
            }
            nodes[utility_name] = sampler_info
    return nodes


def preprocess_bump(node):
    """
    Preprocess bump
    Special processing is done for normal bump
    """
    nodes = {}
    node_name = node["name"]
    node["weight"] = 10

    attributes = node["attributes"]
    # {0: 'bump', 1: 'tangent', 2: 'object'}
    if attributes.get("bumpInterp") == 1:
        node["type"] = "spaceTransform"
        attributes["type"] = 2  # normal
        attributes["invert_x"] = 0
        attributes["invert_y"] = 0
        attributes["invert_z"] = 0
        attributes["from"] = 4  # tangent
        attributes["to"] = 0  # world
        attributes["color_to_signed"] = 1
        attributes["set_normal"] = 1
    nodes[node_name] = node
    return nodes


def preprocess_ramp(node):
    """
    Preprocess ramp
    Maya allows several textures to be used instead of colors.
    We support the most common scenario: mixing two textures.
    In this case we replaces ramp with mix node and rampFloat
    """
    nodes = {}
    node_name = node["name"]
    color_entry_list = {}
    for connection_name, connection in node["connections"].items():
        colorEntryMatch = re.search(r"color_entry_list\[(\d+)\]", connection_name)
        if colorEntryMatch:
            i = int(colorEntryMatch.group(1))
            color_entry_list[i] = connection
    # Get the number of ramp points in Maya
    color_entry_list_size = cmds.getAttr(
        "{node}.colorEntryList".format(node=node_name), size=True
    )
    if color_entry_list_size < 2 and color_entry_list:
        # delete the whole ramp as it does nothing in Katana
        if color_entry_list_size == 1:
            # Get the only dictionary value as we know for sure there is one texture input
            source_connection = color_entry_list.values()[0]
            # Here we create a dummy node with no connections,
            # it will be ignored automatically as it's not of known types.
            # But it can be used to perform renames.
            empty_name = utils.unique_name("Empty")
            empty_node = {
                "connections": {},
                "renamings": {node_name: {"name": source_connection["node"]},},
            }
            nodes[empty_name] = empty_node
        return nodes
    color_entry_list_size = len(color_entry_list)
    if color_entry_list_size > 0 and color_entry_list_size <= 2:
        mix_name = utils.unique_name(node_name + "Mix")
        connections = {
            "mix": {"node": node_name, "original_port": None},
        }
        attributes = {}
        color_entry_list_indices = cmds.getAttr(
            node_name + ".color_entry_list", multiIndices=True
        )
        i = color_entry_list_indices[0]
        if color_entry_list.get(i):
            connections["input1"] = color_entry_list.get(i)
        else:
            attributes["input1"] = cmds.getAttr(
                "{node}.color_entry_list[{index}].{param}".format(
                    node=node_name, index=i, param="color"
                )
            )
        i = color_entry_list_indices[1]
        if color_entry_list.get(i):
            connections["input2"] = color_entry_list.get(i)
        else:
            attributes["input2"] = cmds.getAttr(
                "{node}.color_entry_list[{index}].{param}".format(
                    node=node_name, index=i, param="color"
                )
            )
        mix = {
            "name": mix_name,
            "type": "mix",
            "attributes": attributes,
            "connections": connections,
            "renamings": {node_name: {"name": mix_name},},
        }
        # print 'color_entry_list_size', node, color_entry_list_size
        # print 'color_entry_list', color_entry_list
        # print 'connections', connections
        nodes[mix_name] = mix
        node["type"] = "rampFloat"
    nodes[node_name] = node
    return nodes


def process_network_material(xml_group, node):
    """
    Process NetworkMaterial to remove extra input ports
    """
    if float(cmds.pluginInfo('mtoa', query = True, version = True)[0]) >= 2.0:
        for i in ["arnoldSurface", "arnoldDisplacement"]:
            if i not in node["connections"]:
                parameter = xml_group.find("./port[@name='{param}']".format(param=i))
                xml_group.remove(parameter)
    else:
        for i in ["arnold_surface", "arnoldBump", "arnoldDisplacement"]:
            if i not in node["connections"]:
                parameter = xml_group.find("./port[@name='{param}']".format(param=i))
                xml_group.remove(parameter)


def process_ramp(xml_group, node):
    """
    Process ramp and rampFloat
    """
    attributes = node["attributes"]
    node_name = node["name"]
    if not node_name:
        return
    node_type = node["type"]
    if not node_type:
        return
    connections = node["connections"]
    ramp_input = ""
    if str(attributes["type"]) == "0":
        ramp_type = "v"
        ramp_input = attributes.get("vCoord", "0")
        if connections.get("vCoord"):
            ramp_type = "custom"
            connections["input"] = connections["vCoord"]
            del connections["vCoord"]
    elif str(attributes["type"]) == "1":
        ramp_type = "u"
        ramp_input = attributes.get("uCoord", "0")
        if connections.get("uCoord"):
            ramp_type = "custom"
            connections["input"] = connections["uCoord"]
            del connections["uCoord"]
    elif str(attributes["type"]) == "2":
        ramp_type = "diagonal"
    elif str(attributes["type"]) == "3":
        ramp_type = "radial"
    elif str(attributes["type"]) == "4":
        ramp_type = "circular"
    elif str(attributes["type"]) == "5":
        ramp_type = "box"
    else:
        utils.log.warning(
            'Can\'t translate ramp type for node "{name}"'.format(name=node_name)
        )
        ramp_type = "custom"
    key_value = "color" if node_type == "ramp" else "value"
    interpolation = 0 if attributes["interpolation"] == 0 else 3 if attributes["interpolation"] == 4 else 2
    color_entry_list_size = 2 + cmds.getAttr(
        "{node}.colorEntryList".format(node=node_name), size=True
    )
    color_entry_list = []
    has_connections = False
    color_entry_list_indices = sorted(
        cmds.getAttr(node_name + ".colorEntryList", multiIndices=True)
    )
    for i in color_entry_list_indices:
        if utils.has_connection(
            node, "colorEntryList[{index}].color".format(index=i)
        ):
            has_connections = True
            break
    index = 0
    for i in color_entry_list_indices:
        value_position = cmds.getAttr(
            "{node}.colorEntryList[{index}].{param}".format(
                node=node_name, index=i, param="position"
            )
        )
        if has_connections:
            value_color = index
            index += 1
        else:
            value_color = cmds.getAttr(
                "{node}.colorEntryList[{index}].{param}".format(
                    node=node_name, index=i, param="color"
                )
            )
            value_color = value_color[0]
        color_entry_list.append({key_value: value_color, "position": value_position})
    color_entry_list.sort(key=lambda x: x["position"])
    for dest_key in ["input", "type", "position", key_value, "interpolation", "ramp"]:
        parameter = xml_group.find(
            ".//group_parameter[@name='{param}']".format(param=dest_key)
        )
        if parameter is None:
            continue
        enable_node = parameter.find("*[@name='enable']")
        value_node = parameter.find("*[@name='value']")
        if dest_key in ["input", "type", "ramp"]:
            if not utils.has_connection(node, dest_key):
                enable_node.attrib["value"] = "1"
                if dest_key == "input":
                    value = str(ramp_input)
                elif dest_key == "type":
                    value = ramp_type
                elif dest_key == "ramp":
                    value = str(color_entry_list_size)
                value_node.attrib["value"] = value
            continue
        enable_node.attrib["value"] = "1"
        tuple_size = int(value_node.get("tupleSize", "0"))
        value_node.attrib["size"] = str(tuple_size * color_entry_list_size)
        for i in range(color_entry_list_size - 2):
            if dest_key == "interpolation":
                value = str(interpolation)
            else:
                value = color_entry_list[i][dest_key]
            if dest_key == "color":
                if i == 0:
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 3)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                elif i < (color_entry_list_size - 3):
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 3)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                else:
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 3)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 6)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
        for i in range(color_entry_list_size):
            if dest_key == "interpolation":
                value = str(interpolation)
            else:
                value = color_entry_list[i if i < (color_entry_list_size - 2) 
                                            else (i - 2)][dest_key]
            if dest_key == "interpolation":
                for j in range(tuple_size):
                    sub_value = ET.SubElement(value_node, "number_parameter")
                    sub_value.attrib["name"] = "i" + str(i * tuple_size + j)
                    sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
            if dest_key == "position":
                if i == 0:
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j)
                        sub_value.attrib["value"] = str(0)
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 1)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                elif i < (color_entry_list_size - 3):
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 1)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                else:
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 1)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)
                    for j in range(tuple_size):
                        sub_value = ET.SubElement(value_node, "number_parameter")
                        sub_value.attrib["name"] = "i" + str(i * tuple_size + j + 2)
                        sub_value.attrib["value"] = str(value[j] if tuple_size > 1 else value)


def preprocess_displacement(node):
    """
    Remove the displacement node as there is no counterpart in Katana
    but leave the connections
    """
    nodes = {}
    node_name = node["name"]
    node["weight"] = 20

    node["type"] = "range"
    connection = node.get("connections").get("displacement", {})
    rename = connection.get("node")
    node["connections"] = {
        "input": {
            "node": rename,
            "original_port": utils.get_out_connection(connection),
        },
    }
    nodes[node_name] = node
    return nodes


def override_clamp_params(key, value):
    """
    Maya has an RGB clamp but Katana uses float value so we need to convert
    """
    if key == "min":
        value = min(value)
    if key == "max":
        value = max(value)
    return value


def override_hair_params(key, value):
    """
    Special overrides requested by the artists
    """
    if key == "dualDepth":
        value = 1
    if key == "diffuseIndirectStrength":
        value = 1
    if key == "extraSamplesDiffuse":
        value = 2
    if key == "extraSamplesGlossy":
        value = 2
    return value


def override_material_params(key, value):
    """
    Special overrides requested by the artists
    """
    if key == "specular1IndirectClamp" or key == "specular2IndirectClamp":
        value = 1
    if key == "specular1Distribution" or key == "specular2Distribution":
        value = "ggx"
    return value


def preprocess_image(node): # Arnold 5 add (bate)
    """
    Is the image Arnold 5
    """
    nodes = {}
    node_name = node["name"]
    node["type"] = "image"
    if node["attributes"]["swrap"] == 5:
        node["attributes"]["swrap"] = 0
    if node["attributes"]["twrap"] == 5:
        node["attributes"]["twrap"] = 0
    node["attributes"]["colorSpace"] = "linear"
    nodes[node_name] = node
    return nodes


def preprocess_file(node):
    """
    file to image
    """
    nodes = {}
    node_name = node["name"]
    node["type"] = "image"
    node["attributes"]["filename"] = node["attributes"]["fileTextureName"]
    node["attributes"]["filter"] = 3
    node["attributes"]["multiply"] = node["attributes"]["colorGain"]
    node["attributes"]["offset"] = node["attributes"]["colorOffset"] # Existence of bug
    node["attributes"]["colorSpace"] = "linear"
    if node["attributes"]["uvTilingMode"] == 3:
        filename = node["attributes"]["filename"]
        filename = re.sub(r"\.\d+\.", ".<UDIM>.", filename)
        node["attributes"]["filename"] = filename
    nodes[node_name] = node
    return nodes


def preprocess_network_material(node):
    """
    Preprocess shadingEngine node and remap correct attributes
    """
    nodes = {}
    node_name = node["name"]
    connections = node["connections"]
    new_connections = {}
    if float(cmds.pluginInfo('mtoa', query = True, version = True)[0]) >= 2.0:
        node["type"] = "networkMaterial_ar5"
    else:
        node["type"] = "networkMaterial"
    for i in ["aiSurfaceShader", "surfaceShader", "aiVolumeShader", "volumeShader"]:
        connection = connections.get(i)
        if connection:
            new_connections["arnoldSurface"] = connection
            break
    displacement_connection = connections.get("displacementShader")
    if displacement_connection:
        new_connections["arnoldDisplacement"] = displacement_connection
    node["connections"] = new_connections
    nodes[node_name] = node
    return nodes


def postprocess_network_material(node, all_nodes):
    """
    Rename the networkMaterial node and connect bump
    """
    nodes = {}
    arnold_surface = node["connections"].get("arnoldSurface")
    if arnold_surface:
        shader_node = all_nodes.get(arnold_surface["node"])
        while shader_node and shader_node.get("type") in [
            "aov_write_rgb",
            "aov_write_float",
        ]:
            passthrough = shader_node["connections"].get("beauty")
            if passthrough:
                shader_node = all_nodes.get(passthrough.get("node"))
        if shader_node:
            shader_node_name = shader_node["name"]
            # Remove the output node to reinsert it back with the new name
            all_nodes.pop(shader_node_name, None)
            material_name = shader_node_name
            material_name += "_mtl"
            shader_node_name += "_out"
            shader_node["name"] = shader_node_name
            nodes[shader_node_name] = shader_node
            node["name"] = material_name
            node["connections"]["arnoldSurface"]["node"] = shader_node_name
            node["renamings"] = {
                material_name: {"name": shader_node_name},
            }
            if not float(cmds.pluginInfo('mtoa', query = True, version = True)[0]) >= 2.0:
                bump = shader_node["connections"].get("normalCamera")
                if bump:
                    node["connections"]["arnoldBump"] = bump
                    del shader_node["connections"]["normalCamera"]
            nodes[material_name] = node
    return nodes


def preprocess_multiplyDivide(node):
    nodes = {}
    node_name = node["name"]
    if node["attributes"]["operation"] == 2:
        node["type"] = "divide"
    elif node["attributes"]["operation"] == 3:
        node["type"] = "pow"
        node["attributes"]["base"] = node["attributes"]["input1"]
        node["attributes"]["exponent"] = node["attributes"]["input2"]
    else:
        node["type"] = "multiply"
    print node["type"]
    nodes[node_name] = node
    return nodes


# Preprocess keywords:
# - preprocess
# - postprocess (postprocess at level 0)
# - type (override type)
premap = {
    "displacementShader": {"preprocess": preprocess_displacement,},
    "alSurface": {},
    "alLayer": {},
    "alHair": {},
    "aiStandard": {"type": "standard"},
    "aiVolumeCollector": {"type": "volume_collector"},
    "aiVolumeSampleFloat": {"type": "volume_sample_float"},
    "aiVolumeSampleRgb": {"type": "volume_sample_rgb"},
    "alInputScalar": {},
    "alInputVector": {},
    "luminance": {},
    "alCombineColor": {},
    "alCombineFloat": {},
    "alCurvature": {},
    "alJitterColor": {},
    "alLayerColor": {},
    "alLayerFloat": {},
    "alSwitchColor": {},
    "alSwitchFloat": {},
    "alTriplanar": {},
    "alRemapColor": {},
    "alRemapFloat": {},
    "clamp": {},
    "aiAmbientOcclusion": {"type": "ambientOcclusion"},
    "bump2d": {"preprocess": preprocess_bump},
    "samplerInfo": {"preprocess": preprocess_sampler},
    "aiNoise": {"type": "noise"},
    "alCellNoise": {},
    "alFlake": {},
    "alFlowNoise": {},
    "alFractal": {},
    "aiUserDataFloat": {"type": "user_data_float"},
    "aiUserDataColor": {"type": "user_data_rgb"},
    "aiWriteFloat": {"type": "aov_write_float"},
    "aiWriteColor": {"type": "aov_write_rgb"},
    # Arnold 5 add (bate)
    "aiStandardSurface": {"type": "standard_surface"},
    "aiImage": {"preprocess": preprocess_image},
    "file": {"preprocess": preprocess_file},
    "aiColorCorrect": {"type": "color_correct"},
    "aiNormalMap": {"type": "normal_map"},
    "shadingEngine": {
        "preprocess": preprocess_network_material,
        "postprocess": postprocess_network_material,
    },
    "aiBump2d": {"type": "bump2d_ar5"},
    "multiplyDivide": {"preprocess": preprocess_multiplyDivide},
    "aiMultiply": {"type": "multiply"},
    "aiDivide": {"type": "divide"},
    "aiPow": {"type": "pow"},
    "aiLayerShader": {},
    "ramp": {"preprocess": preprocess_ramp},
    "blendColors": {"type": "mix_rgba"},
}

# Mappings keywords:
# - customColor
# - customProcess
mappings = {
    "alSurface": {
        "customColor": (0.2, 0.36, 0.1),
        "diffuseStrength": {
            "diffuseColor": None,
            "diffuseRoughness": None,
            "backlightStrength": {
                "backlightColor": None,
                "backlightIndirectStrength": None,
            },
            "sssMix": {
                "sssMode": ["cubic", "diffusion", "directional", "empirical"],
                "sssDensityScale": None,
                "sssWeight1": {"sssRadius": None, "sssRadiusColor": None,},
                "sssWeight2": {"sssRadius2": None, "sssRadiusColor2": None,},
                "sssWeight3": {"sssRadius3": None, "sssRadiusColor3": None,},
                "sssTraceSet": None,
            },
            "diffuseExtraSamples": None,
            "sssExtraSamples": None,
            "diffuseIndirectStrength": None,
            "diffuseIndirectClamp": None,
            "diffuseNormal": None,
            "traceSetDiffuse": None,
            "traceSetBacklight": None,
        },
        "specular1Strength": {
            "specular1Color": None,
            "specular1Roughness": None,
            "specular1Anisotropy": None,
            "specular1Rotation": None,
            "specular1FresnelMode": ["dielectric", "metallic"],
            "specular1Ior": None,
            "specular1Reflectivity": None,
            "specular1EdgeTint": None,
            "specular1RoughnessDepthScale": None,
            "specular1ExtraSamples": None,
            "specular1Normal": None,
            "specular1IndirectStrength": None,
            "specular1IndirectClamp": override_material_params,
            "traceSetSpecular1": None,
            "specular1CausticPaths": None,
            "specular1InternalDirect": None,
            # ['beckmann', 'ggx'],
            "specular1Distribution": override_material_params,
        },
        "specular2Strength": {
            "specular2Color": None,
            "specular2Roughness": None,
            "specular2Anisotropy": None,
            "specular2Rotation": None,
            "specular2FresnelMode": ["dielectric", "metallic"],
            "specular2Ior": None,
            "specular2Reflectivity": None,
            "specular2EdgeTint": None,
            "specular2RoughnessDepthScale": None,
            "specular2ExtraSamples": None,
            "specular2Normal": None,
            "specular2IndirectStrength": None,
            "specular2IndirectClamp": override_material_params,
            "traceSetspecular2": None,
            "specular2CausticPaths": None,
            "specular2InternalDirect": None,
            # ['beckmann', 'ggx']),
            "specular2Distribution": override_material_params,
        },
        "transmissionStrength": {
            "transmissionColor": None,
            "transmissionLinkToSpecular1": None,
            "transmissionRoughness": None,
            "transmissionIor": None,
            "ssAttenuationColor": None,
            "ssScattering": None,
            "ssDensityScale": None,
            "ssDirection": None,
            "transmissionRoughnessDepthScale": None,
            "transmissionExtraSamples": None,
            "transmissionEnableCaustics": None,
            "rrTransmissionDepth": None,
            "transmissionClamp": None,
            "ssSpecifyCoefficients": None,
            "ssAbsorption": None,
            "traceSetTransmission": None,
            "transmissionDoDirect": None,
            "transmissionNormal": None,
            "transmissionCausticPaths": None,
        },
        "emissionStrength": {"emissionColor": None,},
        "opacity": None,
    },
    "standard": {
        "customColor": (0.2, 0.36, 0.1),
        "Kd": {
            "color": "Kd_color",
            "diffuseRoughness": "diffuse_roughness",
            "Kb": None,
            "directDiffuse": "direct_diffuse",
            "indirectDiffuse": "indirect_diffuse",
        },
        "Ks": {
            "KsColor": "Ks_color",
            "specularRoughness": "specular_roughness",
            "specularAnisotropy": "specular_anisotropy",
            "specularDistribution": ("specular_distribution", ["beckmann", "ggx"]),
            "specularRotation": "specular_rotation",
            "directSpecular": "direct_specular",
            "indirectSpecular": "indirect_specular",
            "enableGlossyCaustics": "enable_glossy_caustics",
        },
        "Kr": {
            "KrColor": "Kr_color",
            "reflectionExitColor": "reflection_exit_color",
            "reflectionExitUseEnvironment": "reflection_exit_use_environment",
            "enableReflectiveCaustics": "enable_reflective_caustics",
        },
        "Kt": {
            "KtColor": "Kt_color",
            "transmittance": None,
            "refractionRoughness": "refraction_roughness",
            "refractionExitColor": "refraction_exit_color",
            "refractionExitUseEnvironment": "refraction_exit_use_environment",
            "IOR": None,
            "dispersionAbbe": "dispersion_abbe",
            "enableRefractiveCaustics": "enable_refractive_caustics",
            "enableInternalReflections": "enable_internal_reflections",
        },
        "Fresnel": {
            "Krn": None,
            "specularFresnel": "specular_Fresnel",
            "Ksn": None,
            "FresnelUseIOR": "Fresnel_use_IOR",
            "FresnelAffectDiff": "Fresnel_affect_diff",
        },
        "emission": {"emissionColor": "emission_color",},
        "Ksss": {
            "KsssColor": "Ksss_color",
            "sssProfile": ("sss_profile", ["empirical", "cubic"]),
            "sssRadius": "sss_radius",
        },
        "bounceFactor": "bounce_factor",
        "opacity": None,
    },
    "volume_collector": {
        "scatteringSource": ("scattering_source", ["parameter", "channel"]),
        "scatteringChannel": "scattering_channel",
        "scattering": None,
        "scatteringColor": "scattering_color",
        "scatteringIntensity": "scattering_intensity",
        "anisotropy": None,
        "attenuationSource": (
            "attenuation_source",
            ["parameter", "channel", "scattering"],
        ),
        "attenuationChannel": "attenuation_channel",
        "attenuation": None,
        "attenuationColor": "attenuation_color",
        "attenuationIntensity": "attenuation_intensity",
        "attenuationMode": ("attenuation_mode", ["absorption", "extinction"]),
        "emissionSource": ("emission_source", ["parameter", "channel"]),
        "emissionChannel": "emission_channel",
        "emission": None,
        "emissionColor": "emission_color",
        "emissionIntensity": "emission_intensity",
        "positionOffset": "position_offset",
        "interpolation": ["closest", "trilinear", "tricubic"],
    },
    "volume_sample_float": {
        "channel": None,
        "positionOffset": "position_offset",
        "interpolation": ["closest", "trilinear", "tricubic"],
        "inputMin": "input_min",
        "inputMax": "input_max",
        "contrast": None,
        "contrastPivot": "contrast_pivot",
        "bias": None,
        "gain": None,
        "outputMin": "output_min",
        "outputMax": "output_max",
        "clampMin": "clamp_min",
        "clampMax": "clamp_max",
    },
    "volume_sample_rgb": {
        "channel": None,
        "positionOffset": "position_offset",
        "interpolation": ["closest", "trilinear", "tricubic"],
        "gamma": None,
        "hueShift": "hue_shift",
        "saturation": None,
        "contrast": None,
        "contrastPivot": "contrast_pivot",
        "exposure": None,
        "multiply": None,
        "add": None,
    },
    "luminance": {"value": "input",
    },
    "alCombineColor": {
        "input1": None,
        "input2": None,
        "input3": None,
        "combineOp": [
            "multiply 1*2",
            "add 1+2",
            "divide 1/2",
            "subtract 1-2",
            "lerp(1, 2, 3)",
            "dot(1, 2)",
            "distance(1 -> 2)",
            "cross(1, 2)",
        ],
    },
    "alCombineFloat": {
        "input1": None,
        "input2": None,
        "input3": None,
        "combineOp": [
            "multiply 1*2",
            "add 1+2",
            "divide 1/2",
            "subtract 1-2",
            "lerp(1, 2, 3)",
        ],
    },
    "alInputScalar": {
        "input": [
            "facing-ratio",
            "area",
            "face-index",
            "ray-length",
            "ray-depth",
            "User",
        ],
        "userName": None,
        "RMPinputMin": None,
        "RMPinputMax": None,
        "RMPcontrast": None,
        "RMPcontrastPivot": None,
        "RMPbias": None,
        "RMPgain": None,
        "RMPoutputMin": None,
        "RMPoutputMax": None,
        "RMPclampEnable": None,
        "RMPthreshold": None,
        "RMPclampMin": None,
        "RMPclampMax": None,
    },
    "alInputVector": {
        "input": [
            "P",
            "Po",
            "N",
            "Nf",
            "Ng",
            "Ngf",
            "Ns",
            "dPdu",
            "dPdv",
            "Ld",
            "Rd",
            "uv",
            "User",
            "Custom",
        ],
        "userName": None,
        "vector": None,
        "type": ["Point", "Vector"],
        "matrix": None,
        "coordinates": ["cartesian", "spherical", "normalized spherical"],
    },
    "alCurvature": {
        "mode": ["positive", "negative"],
        "samples": None,
        "sampleRadius": None,
        "traceSet": None,
        "RMPinputMin": None,
        "RMPinputMax": None,
        "RMPcontrast": None,
        "RMPcontrastPivot": None,
        "RMPbias": None,
        "RMPgain": None,
        "RMPoutputMin": None,
        "RMPoutputMax": None,
        "RMPclampEnable": None,
        "RMPthreshold": None,
        "RMPclampMin": None,
        "RMPclampMax": None,
        "color1": None,
        "color2": None,
    },
    "alJitterColor": {
        "input": None,
        "minSaturation": None,
        "maxSaturation": None,
        "minGain": None,
        "maxGain": None,
        "minHueOffset": None,
        "maxHueOffset": None,
        "clamp": None,
        "signal": None,
    },
    "alLayerColor": {
        "layer1": None,
        "layer1a": None,
        "layer1blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer2": None,
        "layer2a": None,
        "layer2blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer3": None,
        "layer3a": None,
        "layer3blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer4": None,
        "layer4a": None,
        "layer4blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer5": None,
        "layer5a": None,
        "layer5blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer6": None,
        "layer6a": None,
        "layer6blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer7": None,
        "layer7a": None,
        "layer7blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
        "layer8": None,
        "layer8a": None,
        "layer8blend": [
            "Normal",
            "Lighten",
            "Darken",
            "Multiply",
            "Average",
            "Add",
            "Subtract",
            "Difference",
            "Negation",
            "Exclusion",
            "Screen",
            "Overlay",
            "Soft Light",
            "Hard Light",
            "Color Dodge",
            "Color Burn",
            "Linear Dodge",
            "Linear Burn",
            "Linear Light",
            "Vivid Light",
            "Pin Light",
            "Hard Mix",
            "Reflect",
            "Glow",
            "Phoenix",
        ],
    },
    "alLayerFloat": {
        "layer1": None,
        "layer1a": None,
        "layer2": None,
        "layer2a": None,
        "layer3": None,
        "layer3a": None,
        "layer4": None,
        "layer4a": None,
        "layer5": None,
        "layer5a": None,
        "layer6": None,
        "layer6a": None,
        "layer7": None,
        "layer7a": None,
        "layer8": None,
        "layer8a": None,
    },
    "alSwitchColor": {
        "inputA": None,
        "inputB": None,
        "inputC": None,
        "inputD": None,
        "inputE": None,
        "inputF": None,
        "inputG": None,
        "inputH": None,
        "mix": None,
        "threshold": None,
    },
    "alSwitchFloat": {
        "inputA": None,
        "inputB": None,
        "inputC": None,
        "inputD": None,
        "inputE": None,
        "inputF": None,
        "inputG": None,
        "inputH": None,
        "mix": None,
        "threshold": None,
    },
    "alTriplanar": {
        "customColor": (0.36, 0.25, 0.38),
        "input": None,
        "texture": replace_tx,
        "space": ["world", "object", "Pref"],
        "normal": ["geometric", "smooth", "smooth-NoBump"],
        "tiling": ["regular", "cellnoise"],
        "frequency": None,
        "mipMapBias": None,
        "blendSoftness": None,
        "cellSoftness": None,
        "scalex": None,
        "scaley": None,
        "scalez": None,
        "offsetx": None,
        "offsety": None,
        "offsetz": None,
        "rotx": None,
        "roty": None,
        "rotz": None,
        "rotjitterx": None,
        "rotjittery": None,
        "rotjitterz": None,
    },
    "alRemapColor": {
        "input": None,
        "gamma": None,
        "saturation": None,
        "hueOffset": None,
        "contrast": None,
        "contrastPivot": None,
        "gain": None,
        "exposure": None,
        "mask": None,
    },
    "alRemapFloat": {
        "input": None,
        "RMPinputMin": None,
        "RMPinputMax": None,
        "RMPcontrast": None,
        "RMPcontrastPivot": None,
        "RMPbias": None,
        "RMPgain": None,
        "RMPoutputMin": None,
        "RMPoutputMax": None,
        "RMPclampEnable": None,
        "RMPthreshold": None,
        "RMPclampMin": None,
        "RMPclampMax": None,
        "mask": None,
    },
    "alLayer": {
        "customColor": (0.2, 0.56, 0.1),
        "layer1": None,
        "layer2": None,
        "mix": None,
        "debug": ["off", "layer1", "layer2", "mixer"],
    },
    "clamp": {
        "input": None,
        "min": override_clamp_params,
        "max": override_clamp_params,
    },
    "rampFloat": {
        "customProcess": process_ramp,
        #'uCoord': 'input',
        #'vCoord': 'input',
    },
    "alHair": {
        "customColor": (0.2, 0.36, 0.1),
        "melanin": None,
        "dyeColor": None,
        "specularWidth": None,
        "specularShift": None,
        "opacity": None,
        "randomTangent": None,
        "randomMelanin": None,
        "randomHue": None,
        "randomSaturation": None,
        "glintRolloff": None,
        "transmissionRolloff": None,
        "diffuseStrength": {
            "diffuseColor": None,
            "diffuseScatteringMode": ["kajiya-kay", "dual-scattering"],
            "diffuseForward": None,
            "diffuseBack": None,
        },
        "specular1Strength": {
            "specular1Color": None,
            "specular1WidthScale": None,
            "specular1Shift": None,
        },
        "specular2Strength": {
            "specular2Color": None,
            "specular2WidthScale": None,
            "specular2Shift": None,
            "glintStrength": None,
        },
        "transmissionStrength": {
            "transmissionColor": None,
            "transmissionWidthScale": None,
            "transmissionShift": None,
        },
        "dualDepth": override_hair_params,
        "diffuseIndirectStrength": override_hair_params,
        "extraSamplesDiffuse": override_hair_params,
        "glossyIndirectStrength": None,
        "extraSamplesGlossy": override_hair_params,
        "uparam": None,
        "vparam": None,
        "aovDepth": "aov_depth",
    },
    "ambientOcclusion": {
        "samples": None,
        "spread": None,
        "nearClip": "near_clip",
        "farClip": "far_clip",
        "falloff": None,
        "black": None,
        "white": None,
        "opacity": None,
        "invertNormals": "invert_normals",
        "selfOnly": "self_only",
    },
    "bump2d": {"bumpValue": "bump_map", "bumpDepth": "bump_height",},
    "networkMaterial": {
        "customColor": (0.4, 0.35, 0.2),
        "customProcess": process_network_material,
    },
    "mix": {
        "input1": None,
        "input2": None,
        "mix": None,
        # Inputs in Maya and Katana are crossed!
        "color1": "input2",
        "color2": "input1",
        "blender": "mix",
    },
    "facingRatio": {},
    "two_sided": {"front": None, "back": None,},
    "noise": {
        "octaves": None,
        "distortion": None,
        "lacunarity": None,
        "amplitude": None,
        "scale": None,
        "offset": None,
        "coordSpace": ("coord_space", ["world", "object", "Pref"]),
    },
    "alCellNoise": {
        "space": ["world", "object", "Pref", "UV"],
        "frequency": None,
        "mode": ["features", "chips"],
        "randomness": None,
        "octaves": None,
        "lacunarity": None,
        "RMPinputMin": None,
        "RMPinputMax": None,
        "RMPcontrast": None,
        "RMPcontrastPivot": None,
        "RMPbias": None,
        "RMPgain": None,
        "RMPoutputMin": None,
        "RMPoutputMax": None,
        "RMPclampEnable": None,
        "RMPthreshold": None,
        "RMPclampMin": None,
        "RMPclampMax": None,
        "color1": None,
        "color2": None,
        "smoothChips": None,
        "randomChips": None,
        "chipColor1": None,
        "chipProb1": None,
        "chipColor2": None,
        "chipProb2": None,
        "chipColor3": None,
        "chipProb3": None,
        "chipColor4": None,
        "chipProb4": None,
        "chipColor5": None,
        "chipProb5": None,
        "P": None,
    },
    "alFlake": {
        "space": ["tangent", "world"],
        "amount": None,
        "size": None,
        "divergence": None,
        "P": None,
    },
    "alFlowNoise": {
        "space": ["world", "object", "Pref", "UV"],
        "frequency": None,
        "octaves": None,
        "lacunarity": None,
        "gain": None,
        "angle": None,
        "advection": None,
        "turbulent": None,
        "RMPinputMin": None,
        "RMPinputMax": None,
        "RMPcontrast": None,
        "RMPcontrastPivot": None,
        "RMPbias": None,
        "RMPgain": None,
        "RMPoutputMin": None,
        "RMPoutputMax": None,
        "RMPclampEnable": None,
        "RMPthreshold": None,
        "RMPclampMin": None,
        "RMPclampMax": None,
        "color1": None,
        "color2": None,
        "P": None,
    },
    "alFractal": {
        "mode": ["scalar", "vector"],
        "space": ["world", "object", "Pref", "UV"],
        "scale": None,
        "frequency": None,
        "time": None,
        "octaves": None,
        "distortion": None,
        "lacunarity": None,
        "gain": None,
        "turbulent": None,
        "RMPinputMin": None,
        "RMPinputMax": None,
        "RMPcontrast": None,
        "RMPcontrastPivot": None,
        "RMPbias": None,
        "RMPgain": None,
        "RMPoutputMin": None,
        "RMPoutputMax": None,
        "RMPclampEnable": None,
        "RMPthreshold": None,
        "RMPclampMin": None,
        "RMPclampMax": None,
        "color1": None,
        "color2": None,
        "P": None,
    },
    "spaceTransform": {
        "bumpValue": "input",
        "bumpDepth": "scale",
        "type": ["point", "vector", "normal"],
        "order": ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"],
        "invert_x": None,
        "invert_y": None,
        "invert_z": None,
        "color_to_signed": None,
        "from": ["world", "object", "camera", "screen", "tangent"],
        "to": ["world", "object", "camera", "screen", "tangent"],
        "tangent": None,
        "set_normal": None,
    },
    "range": {
        "input": None,
        "input_min": None,
        "input_max": None,
        "output_min": None,
        "output_max": None,
        "smoothstep": None,
    },
    "user_data_rgb": {"colorAttrName": "attribute", "defaultValue": "default",},
    "user_data_float": {"floatAttrName": "attribute", "defaultValue": "default",},
    "aov_write_rgb": {
        "beauty": "passthrough",
        "input": "aov_input",
        "aovName": "aov_name",
        "blend": "blend_opacity",
    },
    "aov_write_float": {
        "beauty": "passthrough",
        "input": "aov_input",
        "aovName": "aov_name",
    },
    # Arnold 5 add (bate)
    "standard_surface": {
        'customColor': (0.05, 0.26, 0.09),
        'base': {
            'baseColor': 'base_color',
            'diffuseRoughness': 'diffuse_roughness',
            'directDiffuse': 'direct_diffuse',
            'metalness': None,
        },
        'specular': {
            'specularColor': 'specular_color',
            'specularRoughness': 'specular_roughness',
            'specularIOR': 'specular_IOR',
            'specularAnisotropy': 'specular_anisotropy',
            'specularRotation': 'specular_rotation',
        },
        'transmission': {
            'transmissionColor': 'transmission_color',
            'transmissionDepth': 'transmission_depth',
            'transmissionScatter': 'transmission_scatter',
            'transmissionScatterAnisotropy': 'transmission_scatter_anisotropy',
            'transmissionDispersion': 'transmission_dispersion',
            'transmissionExtraRoughness': 'transmission_extra_roughness',
            'transmitAovs': 'transmit_aovs',
        },
        'subsurface': {
            'subsurfaceColor': 'subsurface_color',
            'subsurfaceRadius': 'subsurface_radius',
            'subsurfaceScale': 'subsurface_scale',
            'subsurfaceType': (
                'subsurface_type',
                ['diffusion', 'randomwalk', 'randomwalk_v2']),
            'subsurfaceAnisotropy': 'subsurface_anisotropy',
        },
        'coat': {
            'coatColor': 'coat_color',
            'coatRoughness': 'coat_roughness',
            'coatIOR': 'coat_IOR',
            'coatAnisotropy': 'coat_anisotropy',
            'coatRotation': 'coat_rotation',
            'coatNormal': 'coat_normal',
            '': 'coat_affect_color',  # maya not attr
            '': 'coat_affect_roughness',  # maya not attr
        },
        'sheen': {
            'sheenColor': 'sheen_color',
            'sheenRoughness': 'sheen_roughness',
        },
        'emission': {
            'emissionColor': 'emission_color',
        },
        'thinFilmThickness': 'thin_film_thickness',
        'thinFilmIOR': 'thin_film_IOR',
        'thinWalled': 'thin_walled',
        'opacity': None,
        'normalCamera': 'normal',
        'tangent': None,
        'matte': {
            # katana not attr
            'matteColor': '',
            'matteOpacity': '',
        },
        'caustics': None,
        'internalReflections': 'internal_reflections',
        'exitToBackground': 'exit_to_background',
        'indirectDiffuse': 'indirect_diffuse',
        'indirectSpecular': 'indirect_specular',
        'aovs': {
            'aovId1': 'aov_id1',
            'id1': None,
            'aovId2': 'aov_id2',
            'id2': None,
            'aovId3': 'aov_id3',
            'id3': None,
            'aovId4': 'aov_id4',
            'id4': None,
            'aovId5': 'aov_id5',
            'id5': None,
            'aovId6': 'aov_id6',
            'id6': None,
            'aovId7': 'aov_id7',
            'id7': None,
            'aovId8': 'aov_id8',
            'id8': None,
        }
    },
    "image": {
        "customColor": (0.36, 0.25, 0.38),
        "filename": replace_tx,
        # "useFrameExtension": "", # Retain
        # "frame": "", # Retain
        "filter": ["closest", "bilinear", "bicubic", "smart_bicubic"],
        "mipmapBias": "mipmap_bias",
        "multiply": None,
        "offset": None,
        "colorSpace": "color_space",
        "ignoreMissingTextures": "ignore_missing_textures",
        "missingTextureColor" : "missing_texture_color",
        "uvset": None,
        "uvcoords": None,
        "soffset": None,
        "toffset": None,
        "swrap": ["periodic", "black", "clamp", "mirror", "file"],
        "twrap": ["periodic", "black", "clamp", "mirror", "file"],
        "sscale": None,
        "tscale": None,
        "sflip": None,
        "tflip": None,
        "swapSt": "swap_st",
        "singleChannel": "single_channel",
        "startChannel": "start_channel",
    },
    "color_correct": {
        "customColor": (0.03, 0.35, 0.5),
        "input": None,
        "mask": None,
        "colorCorrection": {
            "gamma": None,
            "hueShift": "hue_shift",
            "saturation": None,
            "contrast": None,
            "contrastPivot": "contrast_pivot",
            "exposure": None,
            "multiply": None,
            "add": None,
            "invert": None,
        },
        "alpha": {
            "alphaIsLuminance": "alpha_is_luminance",
            "alphaMultiply": "alpha_multiply",
            "alphaAdd": "alpha_add",
            "invertAlpha": "invert_alpha",
        },
    },
    "normal_map": {
        "customColor": (0.03, 0.35, 0.5),
        "input": None,
        "strength": None,
        "tangent": None,
        "normal": None,
        "order": (
            "order", 
            ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]),
        "invertX": "invert_x",
        "invertY": "invert_y",
        "invertZ": "invert_z",
        "colorToSigned": "color_to_signed",
        "tangentSpace": "tangent_space",
    },
    "networkMaterial_ar5": {
        "customColor": (0.4, 0.35, 0.2),
        "customProcess": process_network_material,
    },
    "bump2d_ar5": {
        "bumpMap": "bump_map",
        "bumpHeight": "bump_height",
        "normal": None,
    },
    "multiply": {
        "input1": None,
        "input2": None,
    },
    "divide": {
        "input1": None,
        "input2": None,
    },
    "pow": {
        "base": None,
        "exponent": None,
    },
    "aiLayerShader": {
        "customColor": (0.20, 0.26, 0.18),
        "enable1": {
            "name1": None,
            "input1": None,
            "mix1": None,
        },
        "enable2": {
            "name2": None,
            "input2": None,
            "mix2": None,
        },
        "enable3": {
            "name3": None,
            "input3": None,
            "mix3": None,
        },
        "enable4": {
            "name4": None,
            "input4": None,
            "mix4": None,
        },
        "enable5": {
            "name5": None,
            "input5": None,
            "mix5": None,
        },
        "enable6": {
            "name6": None,
            "input6": None,
            "mix6": None,
        },
        "enable7": {
            "name7": None,
            "input7": None,
            "mix7": None,
        },
        "enable8": {
            "name8": None,
            "input8": None,
            "mix8": None,
        },
    },
    "ramp": {
        "customProcess": process_ramp,
        #'uCoord': 'input',
        #'vCoord': 'input',
    },
    "mix_rgba": {
        "input1": None,
        "input2": None,
        "mix": None,
        # Inputs in Maya and Katana are crossed!
        "color1": "input2",
        "color2": "input1",
        "blender": "mix",
    },
}
