# -*- coding: utf-8 -*-
"""
Created on Sat Aug 15 19:16:28 2015

@author: marcus
"""

import mmap
from numpy import dtype, uint16, uint32, fromfile, fromstring, sort
import subprocess
import os.path
import struct

TYPE_SPEC = 1 # FS, %drive_c%, root
TYPE_UNKNOWN = 2
TYPE_FOLDER = 3
TYPE_FILE = 4

[INFO_TYPE_FILE_CONTENT, INFO_TYPE_DIR_CONTENT, INFO_TYPE_UNKNOWN] = range(3)

class decompressor:
    def __init__(self, source, dest_size):
        self.source = source
        self.dest_size = dest_size
    
    MASK32 = 0xffffffff
    
    def decompress(self, ):
        self.source_reg = 0x80000000
        copy_nr_bits = 8
        copy_offset = 1
        self.dest = bytearray(self.dest_size)
        self.dest_pos = 0
        
        while True:
            if self.step(1) == 1:
                self.dest[self.dest_pos] = self.step(shrink_bits) + shrink_offset
                self.dest_pos += 1
            elif self.step(1) == 1:
                size = self.step2() - 2
                if size != 0:
                    val1 = self.step(copy_nr_bits) | ((size - 1) << copy_nr_bits)
                    size = self.step2()
                    if val1 >= 0x10000:
                        size += 3
                    elif val1 >= 0x37ff:
                        size += 2
                    elif val1 >= 0x27f:
                        size += 1
                    elif val1 <= 0x7f:
                        size += 4
                    copy_offset = val1
                else:
                    size = self.step2()
                self.copy_and_increment(copy_offset, size)
            elif self.step(1) == 0:
                val = self.step(7)
                size = self.step(2) + 2
                if val == 0:
                    if size == 0x2:
                        assert self.dest_pos == self.dest_size
                        return bytes(self.dest)
                    copy_nr_bits = self.step(size + 1)
                else:
                    copy_offset = val
                    self.copy_and_increment(copy_offset, size)
            else:
                val = self.step(4)
                if val == 1:
                    self.dest_pos += 1
                elif val > 1:
                    self.dest[self.dest_pos] = self.dest[self.dest_pos - val + 1]
                    self.dest_pos += 1
                elif self.step(1) == 0:
                    shrink_bits = self.step(1) + 7
                    if shrink_bits == 0x8:
                        shrink_offset = 0
                    else:
                        shrink_offset = self.step(8)
                else:
                    while True:
                        for self.dest_pos in range(self.dest_pos, self.dest_pos + 0x100):
                            self.dest[self.dest_pos] = self.step(8)
                        self.dest_pos += 1
                        if self.step(1) == 0:
                            break
                
    def step(self, bits = 1):
        res = 0
        for _ in range(bits):
            #msb = self.source_reg >= 0x80000000
            msb = self.source_reg >> 31
            self.source_reg = (self.source_reg << 1) & self.MASK32
            if self.source_reg == 0:
                self.source_reg = struct.unpack('I', self.source.read(4))[0]
                #msb = self.source_reg >= 0x80000000
                msb = self.source_reg >> 31
                self.source_reg = (self.source_reg << 1) & self.MASK32 | 1
            res = (res << 1) | msb
        
        return res

    def step2(self):
        ret = 1
        while True:
            ret = (ret << 1) + self.step(1)
            if self.step(1) == 0:
                return ret
                
    def copy_and_increment(self, offset, size):
        for self.dest_pos in range(self.dest_pos, self.dest_pos + size):
            self.dest[self.dest_pos] = self.dest[self.dest_pos - offset]
        self.dest_pos += 1


class ThinAppFile:
        
    block_list_dtype = dtype([('dest_pos', uint32),
                              ('pos1', uint32),
                              ('source_pos', uint32),
                              ('pos3', uint32),
                              ('dest_size', uint32),
                              ('source_size', uint32)])
    
    def __init__(self, file, data_offset, file_offset, file_size, noblocks, nrblocks, name):
        if type(file) == str:
            file = open(file, 'r')
        self.file = file
        
        self.pos = 0
        self.data_offset = data_offset
        self.file_offset = file_offset
        self.file_size = file_size
        self.has_blocks = noblocks == 0
        self.nr_blocks = nrblocks
        if self.has_blocks:
            pass
            #assert nrblocks > 0 or file_size == 0
        else:
            assert nrblocks == 0
        self.has_blocks = self.nr_blocks > 0

        if self.has_blocks:
            self.block_list = None
            self.curr_block_nr = -1
            self.curr_block_data = None
            self.curr_block_type = None

        self.name = name 
           
    def decompress(self, b, outsize):
        a = subprocess.Popen(['./thinapp_read_block',str(len(b)+1), str(outsize)],stdout=subprocess.PIPE,stdin=subprocess.PIPE)
#        out = a.communicate(input=chr(0xd7) + b)[0]
        out = a.communicate(input=b'\xd7' + b)[0]
        return out

        
    def read_block(self, block_nr):
        if block_nr == self.curr_block_nr:
            return
        self.read_block_list()
        self.file.seek(self.block_list['source_pos'][block_nr] + self.data_offset)
        
        if self.block_list['source_size'][block_nr] == self.block_list['dest_size'][block_nr]:
            self.curr_block_data = self.file.read(self.block_list['source_size'][block_nr])
            self.curr_block_type = None
        else:
            self.curr_block_type = ord(self.file.read(1))
            if self.curr_block_type == 0xd7:
                if False:
                    d = decompressor(self.file, self.block_list['dest_size'][block_nr])
                    self.curr_block_data = d.decompress()
                else:
                    self.curr_block_data = self.decompress(self.file.read(self.block_list['source_size'][block_nr]), self.block_list['dest_size'][block_nr])
            else:
                self.curr_block_data = self.file.read(self.block_list['source_size'][block_nr] - 1)
        assert len(self.curr_block_data) == self.block_list['dest_size'][block_nr], ((self.curr_block_data), self.block_list['dest_size'][block_nr], self.name, hex(self.curr_block_type))
        self.curr_block_nr = block_nr
        #self.curr_block_outb = self.block_list['dest_size'][block_nr]
            
    
    def read(self, size=-1):
        if size == -1 or self.pos + size > self.file_size:
            size = self.file_size - self.pos

        if not self.has_blocks:
            self.file.seek(self.pos + self.data_offset + self.file_offset)
            self.pos += size
            return self.file.read(size)
        else:
            self.read_block_list()
            out = bytearray(size)
            while size > 0:
                block_nr = self.block_list['dest_pos'].searchsorted(self.pos + 1) - 1
                self.read_block(block_nr)
                #assert self.curr_block_type == 0xd9
                block_pos = self.pos - self.block_list['dest_pos'][block_nr]
                bytes_left = len(self.curr_block_data) - block_pos                 
                read_size = size
                if read_size > bytes_left:
                    read_size = bytes_left
                out[self.pos:self.pos + read_size] = self.curr_block_data[block_pos:block_pos + read_size]
                self.pos += read_size
                size -= read_size
            return bytes(out)
            
    def read_block_list(self):
        if self.block_list == None:
            self.file.seek(self.data_offset + self.file_offset)
            self.block_list = fromfile(self.file, dtype=self.block_list_dtype, count=self.nr_blocks)
            assert (sort(self.block_list['dest_pos']) == self.block_list['dest_pos']).all()

    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        else:
            self.pos = self.file_size + offset
        if self.pos > self.file_size:
            self.pos = self.file_size
        if self.pos < 0:
            self.pos = 0
        
    def tell(self):
        return self.pos

class ThinAppContainer:
    item_dtype = dtype([('type', uint32),
                        ('parent_pos', uint32),
                        ('name_pos',uint32),
                        ('zeros0', uint32,3),
                        ('nr_subitems', uint32),
                        ('nr_subitems2', uint32),
                        ('subitem_list_pos', uint32),
                        ('info_length1', uint32),
                        ('info_list_pos', uint32),
                        ('info_length', uint32),
                        ('zeros1',uint32,2)])
                        
    info_dtype = dtype([('name', uint32),
                        ('data1', uint32),
                        ('size', uint32),
                        ('data3', uint32),
                        ('block', uint32)])
                        
    file_content_info_dtype = dtype([('zero0', uint32),        #0
                              ('noblocks', uint32),     #1
                              ('name', 'S', 24),          #234567
                              ('zero8', uint32),        #8
                              ('unknown9', uint32),  #9
                              ('unknown10', uint32),  #10
                              ('unknown11', uint32),  #11
                              ('unknown12', uint32),  #12
                              ('unknown13', uint32),  #13
                              ('unknown14', uint32),  #14
                              ('zero15', uint32),       #15
                              ('file_size', uint32),    #16
                              ('zero17', uint32),       #17
                              ('unknown18', uint32),   #18
                              ('unknown19', uint32),   #19
                              ('data_offset', uint32),  #20
                              ('zero21', uint32),       #21
                              ('nrblocks', uint32),    #22
                              ('zero23', uint32)])       #23
    
    ROOT_PATTERN = b'8\x00\x00\x00\x01\x00\x00\x00'
    ROOT_POS = 0x40

    def __init__(self, file):
        if type(file) == str:
            file = open(file, 'rb')
        self.file = file
        
        s = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        self.filesystem_offset = s.find(self.ROOT_PATTERN) - self.ROOT_POS

        self.data_offset = 0x100000

        self.root_item = self.get_item_by_pos(self.ROOT_POS)
        self.cwd_item = self.root_item

    def read_raw(self, pos):
        self.file.seek(pos + self.filesystem_offset)        
        size = fromfile(self.file, dtype=uint32, count=1)[0]
        return self.file.read(size)
        
    def read_u32_array(self, pos, count=-1):
        self.file.seek(pos + self.filesystem_offset)        
        l = fromfile(self.file, dtype=uint32, count=1)[0]
        assert l % 4 == 0
        if count == -1:
            count = int(l / 4)
        return fromfile(self.file, dtype=uint32, count=count)

    def read_struct(self, pos, dtype):
        data = self.read_raw(pos)
        assert len(data) == dtype.itemsize
        data = fromstring(data, dtype=dtype, count=1)
        res = {}
        for name in dtype.names:
            if name.startswith('zero'):
                assert (data[name] == 0).all(), data[name]
            else:
                res[name] = data[name][0]
        return res
        
    def read_utf16(self, pos, length=-1):
        data = self.read_raw(pos)
        start = 0
        if length == -1:
            a = fromstring(data, dtype=uint16, count=2)
            assert a[0] == 0
            length = a[1]
            start = 4
        return data[start:length * 2 + start].decode('utf-16')
    
    def read_file_content_info(self, pos):
        info = self.read_struct(pos, self.file_content_info_dtype)
        n = info['name']
        while len(n) < 24:
            n = n + b'\x00'
        n = n.decode('utf-16')
        while len(n) > 0 and n[-1] == '\x00':
            n = n[:-1]
        
        info['name'] = n
        assert info['noblocks'] in [0,1]
        #if info['noblocks'] == 0:
        #    assert info['nrblocks'] > 0 or info['file_size'] == 0, info
        if info['noblocks'] == 1:
            assert info['nrblocks'] == 0, info
        return info

    def read_info(self, pos):
        info = self.read_struct(pos, self.info_dtype)
        assert info['data3'] in [0,1], map(hex, info)

        info['type'] = INFO_TYPE_UNKNOWN
        info['name'] = self.read_utf16(info['name'])
        if info['data1']  == 1:
            info['type'] = INFO_TYPE_DIR_CONTENT
            info['block'] = self.read_utf16(info['block'], info['size'])
        elif info['size'] == 96:
            info['type'] = INFO_TYPE_FILE_CONTENT
            assert info['data1'] == 3
            info['block'] = self.read_file_content_info(info['block'])
        else:
            info['block'] = self.read_u32_array(info['block'])
            #assert len(info['block']) == info['size'] or (len(info['block']), info['size']) == (2, 4) or (len(info['block']), info['size']) == (4, 16) , (info)

        return info
        
    def read_item_data(self, item, get_name=False, get_subitem_list=False, get_info_list=False, get_info_data=False):
        if get_info_data:
            get_info_list = True
        
        if get_name and not 'name' in item:
            item['name'] = self.read_utf16(item['name_pos']) if item['name_pos'] > 0 else None

        if get_subitem_list and not 'subitem_list' in item:
            item['subitem_list'] = self.read_u32_array(item['subitem_list_pos'], item['nr_subitems'])
        
        if get_info_list and not 'info_list' in item:
            item['info_list'] = self.read_u32_array(item['info_list_pos'])
            assert len(item['info_list']) ==item['info_length']
            item['info_list'] = item['info_list'][:item['info_length1']]

        if get_info_data:
            infos = map(self.read_info, item['info_list'])
            for info in infos:
                if info['type'] == INFO_TYPE_FILE_CONTENT:
                    assert 'file_content' not in item.keys()
                    item['file_content'] = info['block']
                elif info['type'] == INFO_TYPE_DIR_CONTENT:
                    if not 'dir_content' in item:
                        item['dir_content'] = []
                    item['dir_content'].append((info['name'], info['block']))
                else:
                    if not 'unknown_info' in item:
                        item['unknown_info'] = []
                    item['unknown_info'].append(info)
                    

    def get_item_by_pos(self, pos):
        item = self.read_struct(pos, self.item_dtype)

        assert item['type'] in [TYPE_UNKNOWN, TYPE_SPEC, TYPE_FOLDER, TYPE_FILE], item['type']
       
        if item['type'] not in [TYPE_FOLDER, TYPE_SPEC]:
            assert item['nr_subitems'] == 0, item['nr_subitems']
            assert item['nr_subitems2'] == 0, item['nr_subitems2']

        if item['parent_pos'] >= 0x80000000:
            item['parent_pos'] = 0

        assert item['nr_subitems'] <= item['nr_subitems2']

        return item
    
    def listdir(self, path='.'):
        item = self.get_item_by_path(path, get_subitem_list=True)
        return self.listdir_by_item(item)
        
    def listdir_by_item(self, item):
        res = []
        for subitem in item['subitem_list']:
            subitem = self.get_item_by_pos(subitem)
            res.append(subitem['name'])
        return res
        
    def listdir_recursive_by_item(self, item, path):
        res = []
        self.read_item_data(item, get_subitem_list=True)
        for subitem in item['subitem_list']:
            subitem = self.get_item_by_pos(subitem)
            self.read_item_data(subitem, get_name=True)
            full_name = os.path.join(path, subitem['name'])
            res.append(full_name)
            res += self.listdir_recursive_by_item(subitem,full_name)
        return res
        
    def listdir_recursive(self, path='.'):
        item = self.get_item_by_path(path)
        return self.listdir_recursive_by_item(item, path)
                
    def get_item_by_path(self, path):
        path = path.split(os.path.sep)
        if path[0] == '':
            curr = self.root_item
            path = path[1:]
        else:
            curr = self.cwd_item

        while len(path) > 0 and path[-1] == '':
            path.pop()

        for p in path:
            if p == '.':
                pass #curr = curr
            elif p == '..':
                if curr['parent_pos'] > 0:
                    curr = self.get_item_by_pos(curr['parent_pos'])
            else:
                found = None
                self.read_item_data(curr, get_subitem_list=True)
                for sub_pos in curr['subitem_list']:
                    sub = self.get_item_by_pos(sub_pos)
                    self.read_item_data(sub, get_name=True)
                    if sub['name'] == p:
                        found = sub_pos
                        break
                if not found:
                    raise FileNotFoundError(2, path)
                curr = self.get_item_by_pos(found)

        return curr
    
    def chdir(self, path):
        self.cwd_item = self.get_item_by_path(path)
        
    def getcwd(self):
        path = []
        curr = self.cwd_item
        while curr:
            self.read_item_data(curr, get_name=True)
            path.insert(0, curr['name'] if curr['name'] else '')
            curr = self.get_item_by_pos(curr['parent_pos']) if curr['parent_pos'] > 0 else None
        return os.path.join(*path)
        
    def open(self, path):
        item = self.get_item_by_path(path)
        self.read_item_data(item, get_info_data=True)
        if not 'file_content' in item.keys():
            raise IsADirectoryError(21, path)
        file_content = item['file_content']        
        file = ThinAppFile(self.file, data_offset=self.data_offset, file_offset=file_content['data_offset'], file_size=file_content['file_size'], noblocks=file_content['noblocks'], nrblocks=file_content['nrblocks'], name=path)
        return file
    
    def is_dir(self, path):
        item = self.get_item_by_path(path)
        self.read_item_data(item, get_info_data=True)
        if item['nr_subitems'] > 0:
            return True 
        return not 'file_content' in item
        
    def extract(self, dest):
        for f in self.listdir_recursive():
            print(f)
            if self.is_dir(f):
                try:
                    os.mkdir(os.path.join(dest, f))
                except:
                    pass
            else:
                file = self.open(f)
                f2 = open(os.path.join(dest, f),'wb')
                f2.write(file.read())
                f2.close()

        
