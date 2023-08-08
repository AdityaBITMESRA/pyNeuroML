#!/usr/bin/env python
#
#   A script which can be used to generate graphical representation of
#   ion channel densities in NeuroML2 cells
#

import logging
import math
import os
import pprint
import typing
from collections import OrderedDict
from sympy import sympify

from neuroml import (
    Cell,
    Cell2CaPools,
    ChannelDensity,
    ChannelDensityGHK,
    ChannelDensityGHK2,
    ChannelDensityNernst,
    ChannelDensityNernstCa2,
    ChannelDensityNonUniform,
    ChannelDensityNonUniformGHK,
    ChannelDensityNonUniformNernst,
    ChannelDensityVShift,
    VariableParameter,
)
from pyneuroml.pynml import get_value_in_si, read_neuroml2_file
from pyneuroml.utils import get_ion_color

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


pp = pprint.PrettyPrinter(depth=6)

height = 18
spacing = 2
width_o = 18
order = 8
width = width_o * order
start = -2
stop = start + order

substitute_ion_channel_names = {"LeakConductance": "Pas"}


def _get_rect(ion_channel, row, max_, min_, r, g, b, extras=False):
    if max_ == 0:
        return ""

    sb = ""

    lmin = max(math.log10(min_), start)
    lmax = min(math.log10(max_), stop)
    xmin = width * (lmin - start) / order
    xmax = width * (lmax - start) / order
    offset = (height + spacing) * row

    sb += "\n<!-- %s %s: %s -> %s (%s -> %s)-->\n" % (
        row,
        ion_channel,
        min_,
        max_,
        lmin,
        lmax,
    )
    sb += (
        '<rect y="'
        + str(offset)
        + '" width="'
        + str(width)
        + '" height="'
        + str(height)
        + '" style="fill:rgb('
        + str(r)
        + ","
        + str(g)
        + ","
        + str(b)
        + ');stroke-width:0;stroke:rgb(10,10,10)"/>\n'
    )

    text = "%s: " % (
        ion_channel
        if ion_channel not in substitute_ion_channel_names
        else substitute_ion_channel_names[ion_channel]
    )

    for i in range(order):
        x = width_o * i
        sb += (
            '<line x1="'
            + str(x)
            + '" y1="'
            + str(offset)
            + '" x2="'
            + str(x)
            + '" y2="'
            + str(height + offset)
            + '" style="stroke:rgb(100,100,100);stroke-width:0.5" />\n'
        )

    if max_ == min_:
        sb += (
            '<circle cx="'
            + str(xmin)
            + '" cy="'
            + str(offset + (height / 2))
            + '" r="2" style="stroke:yellow;fill:yellow;stroke-width:2" />\n'
        )
        text += " %s S/m^2" % format_float(min_)
    else:
        sb += (
            '<line x1="'
            + str(xmin)
            + '" y1="'
            + str(offset + (height / 2))
            + '" x2="'
            + str(xmax)
            + '" y2="'
            + str(offset + (height / 2))
            + '" style="stroke:black;stroke-width:1" />\n'
        )
        sb += (
            '<circle cx="'
            + str(xmin)
            + '" cy="'
            + str(offset + (height / 2))
            + '" r="2" style="stroke:yellow;fill:yellow;stroke-width:2" />\n'
        )
        sb += (
            '<circle cx="'
            + str(xmax)
            + '" cy="'
            + str(offset + (height / 2))
            + '" r="2" style="stroke:red;fill:red;stroke-width:2" />\n'
        )
        text += " %s->%s S/m^2" % (format_float(min_), format_float(max_))

    if extras:
        sb += (
            '<text x="%s" y="%s" fill="black" font-family="Arial" font-size="12">%s</text>\n'
            % (width + 3, offset + height - 3, text)
        )

    return sb


def format_float(dens):
    if dens == 0:
        return 0
    if int(dens) == dens:
        return "%i" % dens
    if dens < 1e-4:
        return "%f" % dens
    ff = "%.4f" % (dens)
    if "." in ff:
        ff = ff.rstrip("0")
    return ff


def generate_channel_density_plots(
    nml2_file, text_densities=False, passives_erevs=False, target_directory=None
):
    nml_doc = read_neuroml2_file(
        nml2_file, include_includes=True, verbose=False, optimized=True
    )

    cell_elements = []
    cell_elements.extend(nml_doc.cells)
    cell_elements.extend(nml_doc.cell2_ca_poolses)
    svg_files = []
    all_info = {}

    for cell in cell_elements:
        info = {}
        all_info[cell.id] = info
        logger.info("Extracting channel density info from %s" % cell.id)
        sb = ""
        ions = {}
        maxes = {}
        mins = {}
        row = 0
        na_ions = []
        k_ions = []
        ca_ions = []
        other_ions = []

        if isinstance(cell, Cell2CaPools):
            cds = (
                cell.biophysical_properties2_ca_pools.membrane_properties2_ca_pools.channel_densities
                + cell.biophysical_properties2_ca_pools.membrane_properties2_ca_pools.channel_density_nernsts
            )
        elif isinstance(cell, Cell):
            cds = (
                cell.biophysical_properties.membrane_properties.channel_densities
                + cell.biophysical_properties.membrane_properties.channel_density_nernsts
            )

        epas = None
        ena = None
        ek = None
        eh = None
        eca = None

        for cd in cds:
            dens_si = get_value_in_si(cd.cond_density)
            logger.info(
                "cd: %s, ion_channel: %s, ion: %s, density: %s (SI: %s)"
                % (cd.id, cd.ion_channel, cd.ion, cd.cond_density, dens_si)
            )

            ions[cd.ion_channel] = cd.ion
            erev_V = get_value_in_si(cd.erev) if hasattr(cd, "erev") else None
            erev = (
                "%s mV" % format_float(erev_V * 1000) if hasattr(cd, "erev") else None
            )

            if cd.ion == "na":
                if cd.ion_channel not in na_ions:
                    na_ions.append(cd.ion_channel)
                ena = erev
                info["ena"] = erev_V
            elif cd.ion == "k":
                if cd.ion_channel not in k_ions:
                    k_ions.append(cd.ion_channel)
                ek = erev
                info["ek"] = erev_V
            elif cd.ion == "ca":
                if cd.ion_channel not in ca_ions:
                    ca_ions.append(cd.ion_channel)
                eca = erev
                info["eca"] = erev_V
            else:
                if cd.ion_channel not in other_ions:
                    other_ions.append(cd.ion_channel)
                if cd.ion == "non_specific":
                    epas = erev
                    info["epas"] = erev_V
                if cd.ion == "h":
                    eh = erev
                    info["eh"] = erev_V

            if cd.ion_channel in maxes:
                if dens_si > maxes[cd.ion_channel]:
                    maxes[cd.ion_channel] = dens_si
            else:
                maxes[cd.ion_channel] = dens_si
            if cd.ion_channel in mins:
                if dens_si < mins[cd.ion_channel]:
                    mins[cd.ion_channel] = dens_si
            else:
                mins[cd.ion_channel] = dens_si

        for ion_channel in na_ions + k_ions + ca_ions + other_ions:
            col = get_ion_color(ions[ion_channel])
            info[ion_channel] = {"max": maxes[ion_channel], "min": mins[ion_channel]}

            if maxes[ion_channel] > 0:
                sb += _get_rect(
                    ion_channel,
                    row,
                    maxes[ion_channel],
                    mins[ion_channel],
                    col[0],
                    col[1],
                    col[2],
                    text_densities,
                )
                row += 1

        if passives_erevs:
            if ena:
                sb += add_text(row, "E Na = %s " % ena)
                row += 1
            if ek:
                sb += add_text(row, "E K = %s " % ek)
                row += 1
            if eca:
                sb += add_text(row, "E Ca = %s" % eca)
                row += 1
            if eh:
                sb += add_text(row, "E H = %s" % eh)
                row += 1
            if epas:
                sb += add_text(row, "E pas = %s" % epas)
                row += 1

            for (
                sc
            ) in cell.biophysical_properties.membrane_properties.specific_capacitances:
                sb += add_text(row, "C (%s) = %s" % (sc.segment_groups, sc.value))

                info["specific_capacitance_%s" % sc.segment_groups] = get_value_in_si(
                    sc.value
                )
                row += 1

            # sb+='<text x="%s" y="%s" fill="black" font-family="Arial">%s</text>\n'%(width/3., (height+spacing)*(row+1), text)

        sb = (
            "<?xml version='1.0' encoding='UTF-8'?>\n<svg xmlns=\"http://www.w3.org/2000/svg\" width=\""
            + str(width + text_densities * 200)
            + '" height="'
            + str((height + spacing) * row)
            + '">\n'
            + sb
            + "</svg>\n"
        )

        print(sb)
        svg_file = nml2_file + "_channeldens.svg"
        if target_directory:
            svg_file = target_directory + "/" + svg_file.split("/")[-1]
        svg_files.append(svg_file)
        sf = open(svg_file, "w")
        sf.write(sb)
        sf.close()
        logger.info("Written to %s" % os.path.abspath(svg_file))

        pp.pprint(all_info)

    return svg_files, all_info


def add_text(row, text):
    return (
        '<text x="%s" y="%s" fill="black" font-family="Arial" font-size="12">%s</text>\n'
        % (width / 3.0, (height + spacing) * (row + 0.5), text)
    )


def get_channel_densities(nml_cell: Cell) -> typing.Dict[str, typing.List[typing.Any]]:
    """Get channel densities from a NeuroML Cell.

    :param nml_src: TODO
    :returns: list of channel densities on the cell

    """
    # order matters because if two channel densities apply conductances to same
    # segments, only the latest value is applied
    channel_densities = OrderedDict()  # type: typing.Dict[str, typing.List[typing.Any]]
    dens = nml_cell.biophysical_properties.membrane_properties.info(
        show_contents=True, return_format="dict"
    )
    for name, obj in dens.items():
        logger.debug(f"Name: {name}")
        # channel_densities; channel_density_nernsts, etc
        if name.startswith("channel_densit"):
            for m in obj["members"]:
                try:
                    channel_densities[m.ion_channel].append(m)
                except KeyError:
                    channel_densities[m.ion_channel] = []
                    channel_densities[m.ion_channel].append(m)

    logger.debug(f"Found channel densities: {channel_densities}")
    return channel_densities


def get_conductance_density_for_segments(
    cell: Cell,
    channel_density: typing.Union[
        ChannelDensity,
        ChannelDensityGHK,
        ChannelDensityGHK2,
        ChannelDensityVShift,
        ChannelDensityNernst,
        ChannelDensityNernstCa2,
        ChannelDensityNonUniform,
        ChannelDensityNonUniformGHK,
        ChannelDensityNonUniformNernst,
    ],
) -> typing.Dict[int, float]:
    """Get conductance density for each segment to be able to generate a morphology
    plot.

    For uniform channel densities, the value is reported in SI units, but for
    non-uniform channel densities, for example ChannelDensityNonUniform, where
    the conductance density can be a function of an arbitrary variable, like
    distance from soma, the conductance density can be provided by an arbitrary
    function. In this case, the units of the conductance are not reported since
    the arbitrary function only provides a magnitude.

    For non-uniform channel densities, we evaluate the provided expression
    using sympy.sympify.

    :param cell: a NeuroML Cell
    :type cell: Cell
    :param channel_density: a channel density object
    :type channel_density: ChannelDensityGHK or ChannelDensityGHK2 or ChannelDensityVShift or ChannelDensityNernst or ChannelDensityNernstCa2 or ChannelDensityNonUniform or ChannelDensityNonUniformGHK or ChannelDensityNonUniformNernst,
    :returns: dictionary with keys as segment ids and the conductance density
        for that segment as the value

    .. versionadded:: 1.0.8

    """
    data = {}
    if "NonUniform" not in channel_density.__class__.__name__:
        logger.debug(f"Got a uniform channel density: {channel_density}")
        segments = []
        segments = cell.get_all_segments_in_group(channel_density.segment_groups)
        # add any segments explicitly listed
        try:
            segments.extend(channel_density.segments)
        except TypeError:
            pass

        for seg in cell.morphology.segments:
            if seg.id in segments:
                value = get_value_in_si(channel_density.cond_density)
                data[seg.id] = 0.00 if value is None else value
            else:
                data[seg.id] = 0.00
    else:
        # get the inhomogeneous param/value from the channel density
        param = channel_density.variable_parameters[0]  # type: VariableParameter
        inhom_val = param.inhomogeneous_value.value
        inhom_expr = sympify(inhom_val)
        inhom_param_id = param.inhomogeneous_value.inhomogeneous_parameters
        logger.debug(f"Inhom value: {inhom_val}, Inhom param id: {inhom_param_id}")

        # get the definision of the inhomogeneous param from the segment group
        seg_group = cell.get_segment_group(param.segment_groups)
        inhom_params = seg_group.inhomogeneous_parameters
        req_inhom_param = None
        for p in inhom_params:
            if p.id == inhom_param_id:
                req_inhom_param = p
                break
        if req_inhom_param is None:
            raise ValueError(
                f"Could not find InhomogeneousValue definition for id: {inhom_param_id}"
            )
        logger.debug(f"InhomogeneousParameter found: {req_inhom_param}")
        expr_variable = req_inhom_param.variable

        segments = cell.get_all_segments_in_group(seg_group)
        data = {}
        for seg in cell.morphology.segments:
            if seg.id in segments:
                distance_to_seg = cell.get_distance(seg.id)
                data[seg.id] = float(inhom_expr.subs(expr_variable, distance_to_seg))
            else:
                data[seg.id] = 0.00

    return data


if __name__ == "__main__":
    generate_channel_density_plots(
        "../../examples/test_data/HHCellNetwork.net.nml", True, True
    )

    generate_channel_density_plots(
        "../../../neuroConstruct/osb/showcase/BlueBrainProjectShowcase/NMC/NeuroML2/cADpyr229_L23_PC_5ecbf9b163_0_0.cell.nml",
        True,
        True,
    )
