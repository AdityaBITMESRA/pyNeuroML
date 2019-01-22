
from pyneuroml import pynml

from pyneuroml.pynml import print_comment_v, print_comment

import os
import sys

line_count = 1
line_index_vs_distals = {}
line_index_vs_proximals = {}

def _get_lines_for_seg_group(cell, sg, type):
    
    global line_count
    global line_index_vs_distals
    global line_index_vs_proximals
    
    seg_ids = []
    lines = []
    
    ord_segs = cell.get_ordered_segments_in_groups([sg])
    
    if sg in ord_segs:
        segs = ord_segs[sg]

        line_template = '%s %s %s %s %s %s %s %s'

        for segment in segs:
            seg_ids.append(segment.id)
            print_comment_v('Seg %s is in %s'%(segment, sg))

            id = int(segment.id)
            
            parent_seg_id = None if not segment.parent else segment.parent.segments
            parent_line = -1
            
            print parent_line
            print parent_seg_id

            if parent_seg_id!=None:
                fract = segment.parent.fraction_along
                if fract < 0.0001: fract = 0
                if abs(fract-1) < 0.0001: fract = 1
                if fract == 1:
                    parent_line = line_index_vs_distals[parent_seg_id]
                elif segment.parent.fraction_along == 0:
                    parent_line = line_index_vs_proximals[parent_seg_id]
                else:
                    raise Exception("Can't handle case where a segment is not connected to the 0 or 1 point along the parent!\n" \
                +"Segment %s is connected %s (%s) along parent %s"%(segment, segment.parent.fraction_along, fract, segment.parent))

            if segment.proximal is not None:
                proximal = segment.proximal

                x = float(proximal.x)
                y = float(proximal.y)
                z = float(proximal.z)
                r = float(proximal.diameter)/2.0

                comment = ' # %s: %s (proximal)'%(segment, sg)
                comment = ''
                        
                lines.append(line_template%(line_count, type, x,y,z,r, parent_line, comment))
                line_index_vs_proximals[id] = line_count
                parent_line = line_count
                line_count+=1
                

            distal = segment.distal

            x = float(distal.x)
            y = float(distal.y)
            z = float(distal.z)
            r = float(distal.diameter)/2.0

            comment = ' # %s: %s '%(segment, sg)
            comment = ''

            lines.append(line_template%(line_count, type, x,y,z,r, parent_line, comment))
            line_index_vs_distals[id] = line_count
            
            line_count+=1

    return lines, seg_ids
        

def convert_to_swc(nml_file_name):
    
    global line_count
    global line_index_vs_distals
    global line_index_vs_proximals
    line_count = 1
    line_index_vs_distals = {}
    line_index_vs_proximals = {}
    
    base_dir = os.path.dirname(os.path.realpath(nml_file_name))
    
    nml_doc = pynml.read_neuroml2_file(nml_file_name, include_includes=True, verbose=False, optimized=True)
    
    lines = []
    
    
    for cell in nml_doc.cells:
        swc_file_name = '%s/%s.swc'%(base_dir, cell.id)
        swc_file = open(swc_file_name, 'w')
        
        print_comment_v("Converting cell %s as found in NeuroML doc %s to SWC..."%(cell.id,nml_file_name))
        
        lines_sg, seg_ids = _get_lines_for_seg_group(cell, 'soma_group', 1)
        soma_seg_count = len(seg_ids)
        lines += lines_sg
        
        lines_sg, seg_ids = _get_lines_for_seg_group(cell, 'dendrite_group', 3)
        dend_seg_count = len(seg_ids)
        lines += lines_sg
        
        lines_sg, seg_ids = _get_lines_for_seg_group(cell, 'axon_group', 2)
        axon_seg_count = len(seg_ids)
        lines += lines_sg
        
        if not len(cell.morphology.segments) == soma_seg_count+dend_seg_count+axon_seg_count:
            raise Exception("The numbers of the segments in groups: soma_group+dendrite_group+axon_group (%i), is not the same as total number of segments (%s)! All bets are off!"%(soma_seg_count+dend_seg_count+axon_seg_count, len(cell.morphology.segments)))
            
        for i in range(len(lines)):
            l = lines[i]
            swc_line = '%s'%(l)
            print(swc_line)
            swc_file.write('%s\n'%swc_line)
            
        swc_file.close()
    
        print("Written to %s"%swc_file_name)    
        

if __name__ == '__main__':
    
    if len(sys.argv)==1: 
        files = ['../../examples/test_data/pyr_4_sym.cell.nml', 
             '../../examples/test_data/bask.cell.nml']
    else:
        files = [sys.argv[1]]
    
    for f in files:
        convert_to_swc(f)