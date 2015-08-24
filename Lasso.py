'''
    this is a doc string
'''

import xml.etree.cElementTree as ET
import re
import codecs
import json
from collections import defaultdict


#  Regex
RE_PROBLEM_CHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
RE_POSTAL_CODE = re.compile(r"^([a-zA-Z]\d[a-zA-Z]( )?\d[a-zA-Z]\d)$")
    #http://stackoverflow.com/questions/16614648/canadian-postal-code-regex

# Default Dicts used in audit functions
def def_dict_2():
    '''
    defaultdict two deep with default of set
    '''
    return defaultdict(lambda: defaultdict(set))
def def_dict_3():
    '''
    defaultdict three deep with default of set
    '''
    return defaultdict(lambda: defaultdict(lambda: defaultdict(set)))

#########################
### Auditing the data ###
#########################

def dictify_element_and_children(element, atr_d=def_dict_2(), st_atr_d=def_dict_3(), s_st_d=def_dict_2(), tag_k_v_dict=def_dict_2()):
    '''
    take a start xml tag

    return:
        1 - attrib_dict (atr_d): should return all potential attributes with a set of all answers
        2 - sub_tag_attrib_dict (st_atr_d): return sub_tag: sub_tag.attrib.keys()
        3 - sub_subtag_dict (s_st_d): return sub_tag: sub_tag.children
        4 - tag_k_v_dict: for tag sub_tag:
    '''
    for key, val in element.attrib.items():
        atr_d[element.tag][key].add(val)
    for sub_tag in element.iter():
        child_set = {el.tag for el in list(sub_tag)}
        if child_set != set():
            s_st_d[element.tag][sub_tag.tag].update(child_set)
        for key, val in sub_tag.attrib.items():
            st_atr_d[element.tag][sub_tag.tag][key].add(val)
        if sub_tag.tag == 'tag':
            tag_k_v_dict[element.tag][sub_tag.attrib['k']].add(sub_tag.attrib['v'])

    return atr_d, st_atr_d, s_st_d, tag_k_v_dict

def summarizes_data_2_tags_deep(filename):
    atr_d = def_dict_2()
    st_atr_d = def_dict_3()
    s_st_d = def_dict_2()
    tag_k_v_dict = def_dict_2()

    for _, element in ET.iterparse(filename):
        dictify_element_and_children(element, atr_d, st_atr_d, s_st_d, tag_k_v_dict)
    return atr_d, st_atr_d, s_st_d, tag_k_v_dict

def check_keys_list(dict_key_list):
    problem_keys = []
    for key in dict_key_list:
        if RE_PROBLEM_CHARS.search(key):
            problem_keys.append(key)
    return problem_keys

def process_audit_address_type(tag_k_v_dict, directions=()):
    street_types = set()
    street_list = wrap_up_tag_k_v_dict(tag_k_v_dict, 'addr:street')

    for val in list(street_list):
        street_name = val
        street_split = street_name.split()
        if street_split[-1] in directions:
            street_types.add(street_split[-2])
        else:
            street_types.add(street_split[-1])

    return street_types

def wrap_up_tag_k_v_dict(tag_k_v_dict, key):
    return tag_k_v_dict['node'][key] | tag_k_v_dict['node'][key] | tag_k_v_dict['way'][key]


##############################
### Load Data into MongoDB ###
##############################


### variable maps to swap out non normal values for normal values

ST_DIR_MAP = {'S': 'South',
              's': 'South',
              'South': 'South',
              'E': 'East',
              'e': 'East',
              'East': 'East',
              'W': 'West',
              'w': 'West',
              'West': 'West',
              'N': 'North',
              'n': 'North',
              'North': 'North'}

ST_TYPE_MAP = {'AVenue': 'Avenue',
               'Ave': 'Avenue',
               'Crescent': 'Cresent',
               'Dr': 'Drive',
               'Dr.': 'Drive',
               'Rd': 'Road',
               'St': 'Street',
               'St.': 'Street',
               'Steet': 'Street'}

PROV_MAP = {'ON': 'ON',
            'Ontario': 'ON',
            'on': 'ON',
            'ontario': 'ON'}

CITY_MAP = {'City of Cambridge': 'Cambridge',
            'City of Kitchener': 'Kitchener',
            'kitchener': 'Kitchener',
            'City of Waterloo': 'Waterloo',
            'waterloo': 'Waterloo',
            'St. Agatha': 'Saint Agatha'}

def map_subin(val, val_map):
    if val in val_map.keys():
        return val_map[val]
    else:
        return val

def update_street(street):
    st_list = street.split()
    if st_list[-1] in ST_DIR_MAP.keys():
        st_list[-1] = map_subin(st_list[-1], ST_DIR_MAP)
        st_list[-2] = map_subin(st_list[-2], ST_TYPE_MAP)
    elif st_list[-1] in ST_TYPE_MAP.keys():
        st_list[-1] = map_subin(st_list[-1], ST_TYPE_MAP)
    return ' '.join(st_list)

def update_address(key, val, addr_dict):
    if key == 'addr:street':
        addr_dict[key[5:]] = update_street(val)
    elif key == 'addr:state':
        if not addr_dict.get('province'):
            addr_dict['province'] = map_subin(val, PROV_MAP)
    elif key == 'addr:province':
        addr_dict[key[5:]] = map_subin(val, PROV_MAP)
    elif key == 'addr:city':
        addr_dict[key[5:]] = map_subin(val, CITY_MAP)
    else:
        addr_dict[key[5:]] = val
    return addr_dict

def shape_xml_tree(xml_tree):
    '''
    takes xml tree with tag 'node', 'way', or 'relation'

    Unpackes into json compatible dict and list structure.
    returns dictionary

    {'type':    xml_tree.tag,

     'id':      int(xml_tree('id')),

     'pos':     [float(xml_tree('lat')),
                 float(xml_tree('lon'))],

     'created': {'version':     int(xml_tree('uid')),
                 'changeset':   int(xml_tree('changeset')),
                 'timestamp':   xml_tree('timestamp'),
                 'user':        xml_tree('user'),
                 'uid':         int(xml_tree('uid'))},

     'address': {'housenumber': tag_tag['addr:housenumber'],
                 'postcode': tag_tag['addr:postcode'],
                 'street': tag_tag['addr:street'], ...},

     'member':  [{'type': member_tag('type'),
                  'ref':  int(member_tag('ref')),
                  'role': member_tag('role')},
                 {..........................}],

     'node_refs':[int(nd_tag['ref']),
                  int(nd_tag['ref']), ... ],

      tag['k']:  tag_tag['v'],
      tag['k']:  tag_tag['v'], ... }

    '''
    ### returns an empty element if the xml_tree is not a node, way or relation
    if xml_tree.tag not in ['node', 'way', 'relation']:
        return {}

    element = {}

    ### Tag:
    element['type'] = xml_tree.tag

    ### Attributes:
    element['id'] = int(xml_tree.attrib.get('id'))

    if xml_tree.tag == 'node':
        pos = [float(xml_tree.attrib.get('lat')), float(xml_tree.attrib.get('lon'))]
        element['pos'] = pos

    element['created'] = {}
    for key, val in xml_tree.attrib.items():
        if key in ["uid", "version", "changeset"]:
            element['created'][key] = int(val)
        if key in ["user", "timestamp"]:
            element['created'][key] = val

    ### sub tags of xml_tree
    # dicts and lists for constucted values
    node_refs = []
    members = []
    address = {}

    # looping though each sub tag of xml_tree
    for sub_tag in xml_tree.iter():

        ### sub tag of 'tag'
        if sub_tag.tag == 'tag':
            key = sub_tag.attrib['k']
            val = sub_tag.attrib['v']

            ### addr: tags are sent to update_address function
            if key[0:5] == 'addr:':
                address = update_address(key, val, address)

            ### merge 'fixme' and 'FIXME' into 'FIXME'
            elif key in ['fixme', 'FIXME']:
                if element.get('FIXME'):
                    element['FIXME'] += '\nFIXME: ' + val
                else:
                    element['FIXME'] = val

            ### all other tag tags get added as k:v pairs
            else:
                element[key] = val

        ### sub tag of 'nd'
        elif sub_tag.tag == 'nd':
            node_refs.append(int(sub_tag.attrib['ref']))

        ### sub tag of 'member'
        elif sub_tag.tag == 'member':
            mem = {}
            for key, val in sub_tag.attrib.items():
                if val:
                    if key == 'ref':
                        mem[key] = int(val)
                    else:
                        mem[key] = val
            members.append(mem)

    ### append all the constructed vaules
    if node_refs:
        element['nd'] = node_refs
    if members:
        element['member'] = members
    if address:
        element['addr'] = address

    return element

def process_map(file_in, pretty=False):
    file_out = "{0}.json".format(file_in)
    data = []
    with codecs.open(file_out, "w") as file_out:
        for _, xml_tree in ET.iterparse(file_in):
            element = shape_xml_tree(xml_tree)
            if element:
                data.append(element)
                if pretty:
                    file_out.write(json.dumps(element, indent=4)+"\n")
                else:
                    file_out.write(json.dumps(element) + "\n")
    return data

if __name__ == '__main__':
    pass
