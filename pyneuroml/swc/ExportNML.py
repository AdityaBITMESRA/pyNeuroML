import logging
import tempfile
from typing import Dict, List, Optional, Set

import neuroml.writers as writers
from LoadSWC import SWCGraph, SWCNode, load_swc
from neuroml import (
    Cell,
    Member,
    Morphology,
    NeuroMLDocument,
    Property,
    Segment,
    SegmentGroup,
)
from neuroml.nml.nml import Point3DWithDiam, SegmentParent

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="neuroml_conversion.log",
    filemode="w",
)
logger = logging.getLogger(__name__)


class NeuroMLWriter:
    """
    A class to convert SWC graph data to NeuroML format.

    This class takes an SWC graph and converts it into a NeuroML representation,
    handling different neuron segment types and creating appropriate segment groups.
    """

    def __init__(self, swc_graph: SWCGraph) -> None:
        """
        Initialize the NeuroMLWriter with an SWC graph.

        Args:
            swc_graph (SWCGraph): The SWC graph to be converted to NeuroML.
        """
        logger.info("Initializing NeuroMLWriter")
        self.swc_graph = swc_graph
        self.points = swc_graph.nodes
        self.section_types = [
            "undefined",
            "soma",
            "axon",
            "basal dendrite",
            "apical dendrite",
        ]
        self.morphology_origin = swc_graph.metadata.get("ORIGINAL_SOURCE", "Unknown")
        self.cell = None
        self.nml_doc = None
        self.point_indices_vs_seg_ids = {}
        self.next_segment_id = 0
        self.processed_nodes = set()
        self.segment_types = {}
        self.segment_groups = {
            "all": set(),
            "soma_group": set(),
            "axon_group": set(),
            "dendrite_group": set(),
            "basal_dendrite": set(),
            "apical_dendrite": set(),
        }
        logger.debug(f"NeuroMLWriter initialized with {len(self.points)} points")

    def create_cell(self) -> Cell:
        """
        Create a Cell object for the NeuroML representation.

        Returns:
            Cell: The created Cell object.
        """
        logger.info("Creating Cell object")
        cell_name = self.get_cell_name()
        notes = f"Neuronal morphology exported from Python Based Converter. Original file: {self.morphology_origin}"
        self.cell = Cell(id=cell_name, notes=notes)
        self.cell.morphology = Morphology(id=f"morphology_{cell_name}")
        logger.debug(f"Created Cell object with name: {cell_name}")
        return self.cell

    def get_cell_name(self) -> str:
        """
        Generate a cell name based on the morphology origin.

        Returns:
            str: The generated cell name.
        """
        logger.debug("Generating cell name")
        cell_name = "cell1"
        try:
            cell_name = (
                self.morphology_origin.split("/")[-1]
                .replace(".swc", "")
                .replace(".", "_")
                .replace("-", "_")
            )
            if cell_name[0].isdigit():
                cell_name = "Cell_" + cell_name
        except Exception as e:
            logger.error(f"Error in generating cell name: {e}")
        logger.debug(f"Generated cell name: {cell_name}")
        return cell_name

    def nml_string(self) -> str:
        """
        Generate the NeuroML representation as a string.

        Returns:
            str: The NeuroML representation as a string.
        """
        logger.info("Starting NeuroML generation")
        if (
            len(self.points) < 2
            or len(self.section_types) < 2
            or self.section_types[1].lower() != "soma"
        ):
            logger.error("Null data or section types in nmlWrite")
            return ""

        self.create_cell()
        start_point = self.find_start_point()

        logger.debug(f"Cell name: {self.cell.id}")
        logger.debug(f"Start point: {start_point}")

        self.parse_tree(start_point, start_point)
        self.create_segment_groups()

        self.nml_doc = NeuroMLDocument(id=self.cell.id)
        self.nml_doc.cells.append(self.cell)

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            writers.NeuroMLWriter.write(self.nml_doc, temp_file)
            temp_file_path = temp_file.name

        with open(temp_file_path, "r") as temp_file:
            nml_content = temp_file.read()

        logger.info("NeuroML generation completed")
        return nml_content

    def find_start_point(self) -> SWCNode:
        """
        Find the starting point (soma) in the SWC graph.

        Returns:
            SWCNode: The starting point (soma) of the neuron.
        """
        logger.debug("Finding start point (soma)")
        for point in self.points:
            if point.type == SWCNode.SOMA:
                logger.debug(f"Soma found: {point}")
                return point
        logger.warning("No soma points found, using first point")
        return self.points[0]

    def parse_tree(
        self,
        parent_point: SWCNode,
        this_point: SWCNode,
    ) -> None:
        """
        Recursively parse the SWC tree to create NeuroML segments.

        Args:
            parent_point (SWCNode): The parent point of the current point.
            this_point (SWCNode): The current point being processed.
        """
        if this_point.id in self.processed_nodes:
            logger.debug(f"Point {this_point.id} already processed, skipping")
            return

        logger.debug(f"Parsing tree: Point {this_point.id}, Type {this_point.type}")

        type_change = this_point.type != parent_point.type
        new_branch = len(parent_point.children) > 1 if parent_point else False

        if this_point.type == SWCNode.SOMA:
            self.handle_soma(this_point, parent_point)
        else:
            if this_point.id not in self.processed_nodes:
                logger.debug(f"Creating segment for point {this_point.id}")
                self.create_segment(this_point, parent_point, new_branch or type_change)
                self.processed_nodes.add(this_point.id)
            else:
                logger.debug(
                    f"Point {this_point.id} already processed, skipping segment creation"
                )

        self.processed_nodes.add(this_point.id)

        for child_point in this_point.children:
            if child_point.id not in self.processed_nodes:
                self.parse_tree(this_point, child_point)

    def handle_soma(
        self,
        this_point: SWCNode,
        parent_point: SWCNode,
    ) -> None:
        """
        Handle the creation of soma segments.
         Handle the creation of soma segments based on different soma representation cases.
         This method implements the soma representation guidelines as described in
        "Soma format representation in NeuroMorpho.Org as of version 5.3".
         For full details, see: https://github.com/NeuroML/Cvapp-NeuroMorpho.org/blob/master/caseExamples/SomaFormat-NMOv5.3.pdf
          The method handles the following cases:
         1. Single contour (most common, ~80% of cases):
          Converted to a three-point soma cylinder.
         2. Soma absent (~8% of cases):
          Not handled in this method (no changes made).
         3. Multiple contours (~5% of cases):
          Converted to a three-point soma cylinder, averaging all contour points.
         4. Multiple cylinders (~4% of cases):
          Kept as is, no conversion needed.
         5. Single point (~3% of cases):
          Converted to a three-point soma cylinder.
         The three-point soma representation consists of:
         - First point: Center of the soma
         - Second point: Shifted -r_s in y-direction
         - Third point: Shifted +r_s in y-direction
         Where r_s is the equivalent radius computed from the soma surface area.
         This method specifically handles cases 1, 3, and 5. Case 2 is not applicable,
         and case 4 is handled implicitly by not modifying the existing representation.

        Args:
            this_point (SWCNode): The current soma point being processed.
            parent_point (SWCNode): The parent point of the current soma point.
        """
        logger.debug(f"Handling soma point: {this_point.id}")

        if this_point.id in self.processed_nodes:
            logger.debug(f"Soma point {this_point.id} already processed, skipping")
            return

        soma_points = [p for p in self.points if p.type == SWCNode.SOMA]
        if len(soma_points) == 3:
            if this_point.id == soma_points[0].id:
                logger.debug("Processing first point of 3-point soma")
                middle_point = soma_points[1]
                end_point = soma_points[2]

                segment = Segment(
                    id=self.next_segment_id, name=f"Seg_{self.next_segment_id}"
                )
                segment.proximal = Point3DWithDiam(
                    x=middle_point.x,
                    y=middle_point.y,
                    z=middle_point.z,
                    diameter=2 * middle_point.radius,
                )
                segment.distal = Point3DWithDiam(
                    x=this_point.x,
                    y=this_point.y,
                    z=this_point.z,
                    diameter=2 * this_point.radius,
                )
                self.cell.morphology.segments.append(segment)
                self.point_indices_vs_seg_ids[this_point.id] = self.next_segment_id
                self.segment_types[self.next_segment_id] = SWCNode.SOMA
                self.add_segment_to_groups(self.next_segment_id, SWCNode.SOMA)
                self.next_segment_id += 1

                segment = Segment(
                    id=self.next_segment_id, name=f"Seg_{self.next_segment_id}"
                )
                segment.parent = SegmentParent(segments=self.next_segment_id - 1)
                segment.distal = Point3DWithDiam(
                    x=end_point.x,
                    y=end_point.y,
                    z=end_point.z,
                    diameter=2 * end_point.radius,
                )
                self.cell.morphology.segments.append(segment)
                self.point_indices_vs_seg_ids[end_point.id] = self.next_segment_id
                self.segment_types[self.next_segment_id] = SWCNode.SOMA
                self.add_segment_to_groups(self.next_segment_id, SWCNode.SOMA)
                self.next_segment_id += 1

            elif (
                this_point.id == soma_points[1].id or this_point.id == soma_points[2].id
            ):
                pass  # These points are already handled

        elif len(soma_points) == 1:
            logger.debug("Processing single-point soma")
            segment = Segment(
                id=self.next_segment_id, name=f"soma_Seg_{self.next_segment_id}"
            )
            segment.proximal = Point3DWithDiam(
                x=this_point.x,
                y=this_point.y,
                z=this_point.z,
                diameter=2 * this_point.radius,
            )
            segment.distal = Point3DWithDiam(
                x=this_point.x,
                y=this_point.y,
                z=this_point.z,
                diameter=2 * this_point.radius,
            )
            self.cell.morphology.segments.append(segment)
            self.point_indices_vs_seg_ids[this_point.id] = self.next_segment_id
            self.segment_types[self.next_segment_id] = SWCNode.SOMA
            self.add_segment_to_groups(self.next_segment_id, SWCNode.SOMA)
            self.next_segment_id += 1

        else:
            sorted_soma_points = sorted(soma_points, key=lambda p: p.x)

            if this_point == sorted_soma_points[0]:
                logger.debug("Processing multi-point soma")

                for i, current_point in enumerate(sorted_soma_points):
                    if current_point.id not in self.processed_nodes:
                        segment = Segment(
                            id=self.next_segment_id,
                            name=f"soma_Seg_{self.next_segment_id}",
                        )

                        if i == 0:
                            segment.proximal = Point3DWithDiam(
                                x=current_point.x,
                                y=current_point.y,
                                z=current_point.z,
                                diameter=2 * current_point.radius,
                            )
                        else:
                            segment.parent = SegmentParent(
                                segments=self.next_segment_id - 1
                            )

                        if i < len(sorted_soma_points) - 1:
                            next_point = sorted_soma_points[i + 1]
                            segment.distal = Point3DWithDiam(
                                x=next_point.x,
                                y=next_point.y,
                                z=next_point.z,
                                diameter=2 * next_point.radius,
                            )
                        else:
                            segment.distal = Point3DWithDiam(
                                x=current_point.x,
                                y=current_point.y,
                                z=current_point.z,
                                diameter=2 * current_point.radius,
                            )

                        self.cell.morphology.segments.append(segment)
                        self.point_indices_vs_seg_ids[current_point.id] = (
                            self.next_segment_id
                        )
                        self.segment_types[self.next_segment_id] = SWCNode.SOMA
                        self.add_segment_to_groups(self.next_segment_id, SWCNode.SOMA)
                        self.processed_nodes.add(current_point.id)

                        self.next_segment_id += 1

            elif this_point != sorted_soma_points[0]:
                logger.debug(f"Soma point {this_point.id} not the first, skipping")

        self.processed_nodes.add(this_point.id)

    def create_segment(
        self,
        this_point: SWCNode,
        parent_point: SWCNode,
        new_branch: bool,
    ) -> None:
        """
        Create a NeuroML segment from an SWC point.

        Args:
            this_point (SWCNode): The current point being processed.
            parent_point (SWCNode): The parent point of the current point.
            new_branch (bool): Whether this point starts a new branch.
        """

        logger.debug(
            f"Creating segment: Point {this_point.id}, Type {this_point.type}, Parent {parent_point.id}"
        )
        seg_id = self.next_segment_id
        self.next_segment_id += 1

        segment_type = (
            self.section_types[this_point.type]
            if this_point.type < len(self.section_types)
            else f"type_{this_point.type}"
        )
        segment = Segment(id=seg_id, name=f"{segment_type}_Seg_{seg_id}")

        is_branch_point = len(parent_point.children) > 1
        is_type_change = this_point.type != parent_point.type

        if parent_point.id in self.point_indices_vs_seg_ids:
            parent_seg_id = self.point_indices_vs_seg_ids[parent_point.id]
            segment.parent = SegmentParent(segments=parent_seg_id)

        if is_type_change:
            segment.proximal = Point3DWithDiam(
                x=this_point.x,
                y=this_point.y,
                z=this_point.z,
                diameter=2 * this_point.radius,
            )

            if this_point.children:
                next_point = this_point.children[0]
                segment.distal = Point3DWithDiam(
                    x=next_point.x,
                    y=next_point.y,
                    z=next_point.z,
                    diameter=2 * next_point.radius,
                )
            else:
                segment.distal = Point3DWithDiam(
                    x=this_point.x,
                    y=this_point.y,
                    z=this_point.z,
                    diameter=2 * this_point.radius,
                )

            print(f"Processed nodes: {self.processed_nodes}")
        elif is_branch_point:
            segment.proximal = Point3DWithDiam(
                x=parent_point.x,
                y=parent_point.y,
                z=parent_point.z,
                diameter=2 * parent_point.radius,
            )
            segment.distal = Point3DWithDiam(
                x=this_point.x,
                y=this_point.y,
                z=this_point.z,
                diameter=2 * this_point.radius,
            )
        elif this_point.id not in self.processed_nodes:
            segment.distal = Point3DWithDiam(
                x=this_point.x,
                y=this_point.y,
                z=this_point.z,
                diameter=2 * this_point.radius,
            )

        self.cell.morphology.segments.append(segment)
        self.point_indices_vs_seg_ids[this_point.id] = seg_id
        self.segment_types[seg_id] = this_point.type
        self.add_segment_to_groups(seg_id, this_point.type)

        self.processed_nodes.add(this_point.id)

        logger.debug(f"Created segment {seg_id} for point {this_point.id}")

    def add_segment_to_groups(self, seg_id: int, segment_type: int) -> None:
        """
        Add a segment to the appropriate segment groups.

        Args:
            seg_id (int): The ID of the segment to add.
            segment_type (int): The type of the segment.
        """
        groups = self.get_groups_for_type(segment_type)
        for group in groups:
            self.segment_groups[group].add(seg_id)

    def get_groups_for_type(self, segment_type: int) -> List[str]:
        """
        Get the list of group names a segment should belong to based on its type.

        Args:
            segment_type (int): The type of the segment.

        Returns:
            List[str]: A list of group names the segment should belong to.
        """
        groups = ["all"]
        if segment_type == SWCNode.SOMA:
            groups.extend(["soma_group"])
        elif segment_type == SWCNode.AXON:
            groups.extend(["axon_group"])
        elif segment_type == SWCNode.BASAL_DENDRITE:
            groups.extend(["basal_dendrite", "dendrite_group"])
        elif segment_type == SWCNode.APICAL_DENDRITE:
            groups.extend(["apical_dendrite", "dendrite_group"])
        elif segment_type >= 5:
            groups.append("dendrite_group")
        return groups

    def create_segment_groups(self) -> None:
        """
        Create NeuroML segment groups based on the segments created.
        """
        logger.info("Creating segment groups")

        for group_name, members in self.segment_groups.items():
            if members:
                group = SegmentGroup(id=group_name)
                for member_id in sorted(members):
                    group.members.append(Member(segments=member_id))
                self.cell.morphology.segment_groups.append(group)

        root_segment_id = min(
            seg_id
            for seg_id, seg_type in self.segment_types.items()
            if seg_type == SWCNode.SOMA
        )

        self.cell.create_unbranched_segment_group_branches(
            root_segment_id,
            use_convention=True,
            reorder_segment_groups=True,
            optimise_segment_groups=True,
        )

        self.cell.properties.append(
            Property(tag="cell_type", value="converted_from_swc")
        )

        logger.info("Segment groups created successfully")

    def print_soma_segments(self) -> None:
        """
        Print information about the soma segments for debugging purposes.
        """
        logger.info("Printing soma segments:")
        for segment in self.cell.morphology.segments:
            if self.segment_types.get(segment.id) == SWCNode.SOMA:
                print(f"Soma Segment ID: {segment.id}")
                print(f"  Name: {segment.name}")
                if segment.proximal:
                    print(
                        f"  Proximal: x={segment.proximal.x}, y={segment.proximal.y}, z={segment.proximal.z}, diameter={segment.proximal.diameter}"
                    )
                print(
                    f"  Distal: x={segment.distal.x}, y={segment.distal.y}, z={segment.distal.z}, diameter={segment.distal.diameter}"
                )
                if segment.parent:
                    print(f"  Parent Segment ID: {segment.parent.segments}")
                print()

    def export_to_nml_file(self, filename: str) -> None:
        """
        Export the NeuroML representation to a file.

        Args:
            filename (str): The name of the file to export to.
        """
        if self.nml_doc is None:
            self.nml_string()

        writers.NeuroMLWriter.write(self.nml_doc, filename)
        logger.info(f"NeuroML file exported to: {filename}")
