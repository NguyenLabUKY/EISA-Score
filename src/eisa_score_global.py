#!/usr/bin/env python

"""
Introduction:
    EISA score global surface area

Author:
    Masud Rana (masud.rana@uky.edu)
    
Date last modified:
    May 26, 2022

"""

import os
import numpy as np
import pandas as pd
from biopandas.pdb import PandasPdb
from biopandas.mol2 import PandasMol2

import numba_utils_methods as nmb
from element_interactive_density import ElementInteractiveDensity

import time


class EISA_Score_Global_Surface():
    def __init__(self, path, pdbid, kernel_type='exponential',
                 kernel_tau=1.0, kernel_power=2.0, cutoff=7.0,
                 mesh_size=0.5):

        self.path = path  # path to pdbbind dataset
        self.pdbid = pdbid
        self.cutoff = cutoff

        self.mesh_size = mesh_size

        self.kernel_type = kernel_type
        self.kernel_tau = kernel_tau
        self.kernel_power = kernel_power

        self.protein_heavy_atom = {
            'C': 1.7,
            'N': 1.55,
            'O': 1.52,
            'S': 1.8
        }

        self.ligand_heavy_atom = {
            'H': 1.2,
            'C': 1.7,
            'N': 1.55,
            'O': 1.52,
            'S': 1.8,
            'P': 1.8,
            'F': 1.8,
            'Cl': 1.47,
            'Br': 1.75,
            'I': 1.98
        }

        self.num_stat_measure = 6  # sum,mean,median,std,max,and min

        self.isovalue_list = np.arange(0.05, 0.8, 0.05)

    def get_features(self):

        protein_len = len(self.protein_heavy_atom)
        ligand_len = len(self.ligand_heavy_atom)

        num_stat_measure = self.num_stat_measure
        num_features = protein_len*ligand_len*num_stat_measure
        final_features_mat = np.zeros([1, num_features])

        folder = str(self.pdbid)

        p_file_path = f'{self.path}/{folder}/{folder}_protein.pdb'

        l_file_path = f'{self.path}/{folder}/{folder}_ligand.mol2'

        protein = PandasPdb().read_pdb(p_file_path)

        protein_df = protein.df['ATOM']

        ligand = PandasMol2().read_mol2(l_file_path)

        lig_unique_atom_types = ligand.df['atom_type'].unique()  
        
        ligand.df['element_symbol'] = ''

        # Loop over the ligand unique atom type and assign corresponding element symbol

        for val in lig_unique_atom_types:
            if(val[:2] == 'Br'):
                ligand.df.loc[(ligand.df['atom_type'] == val),
                              'element_symbol'] = val[:2]
            elif(val[:2] == 'Cl'):
                ligand.df.loc[(ligand.df['atom_type'] == val),
                              'element_symbol'] = val[:2]
            else:
                ligand.df.loc[(ligand.df['atom_type'] == val),
                              'element_symbol'] = val[0]

        # Loop over all protein and ligand heavy atom
        pair_wise_features = np.zeros(
            (ligand_len*protein_len, num_stat_measure))

        atomic_pair_count = 0

        for i, l_atom_type in enumerate(self.ligand_heavy_atom.keys()):
            
            ligand_atom_type = l_atom_type
            ligand_vdW = self.ligand_heavy_atom[l_atom_type]
            ligand_df_slice = ligand.df[ligand.df['element_symbol']
                                        == ligand_atom_type]

            l_xyz = ligand_df_slice[['x', 'y', 'z']].values

            for j, p_atom_type in enumerate(self.protein_heavy_atom.keys()):
				
                protein_atom_type = p_atom_type
                protein_vdW = self.protein_heavy_atom[p_atom_type]
                protein_df_slice = protein_df[protein_df['element_symbol'] 
                                              == protein_atom_type]

                p_xyz = protein_df_slice[['x_coord', 'y_coord', 'z_coord']].values

                dmat = nmb.distance_matrix(l_xyz, p_xyz)

                index = np.where(dmat < self.cutoff)
                l_index = np.unique(index[0])
                p_index = np.unique(index[1])
                ei_xyz = np.concatenate((l_xyz, p_xyz[p_index, :]))
                
                if np.size(ei_xyz) != 0:
                    bf = 2.0
                    x_left = min(ei_xyz[:, 0])-bf
                    x_right = max(ei_xyz[:, 0])+bf
                    y_left = min(ei_xyz[:, 1])-bf
                    y_right = max(ei_xyz[:, 1])+bf
                    z_left = min(ei_xyz[:, 2])-bf
                    z_right = max(ei_xyz[:, 2])+bf

                    h = self.mesh_size

                    x = np.arange(x_left, x_right, h)
                    y = np.arange(y_left, y_right, h)
                    z = np.arange(z_left, z_right, h)

                    nx, ny, nz = len(x), len(y), len(z)

                    eid_class = ElementInteractiveDensity(kernel_type=self.kernel_type,
                                                          kernel_tau=self.kernel_tau,
                                                          kernel_power=self.kernel_power,
                                                          ligand_vdW=ligand_vdW,
                                                          protein_vdW=protein_vdW
                                                          )

                    rho = eid_class.main(nx, ny, nz, x, y, z,
                                         ei_xyz)

                    rho_max = max(rho.flatten())

                    if rho_max != 0:
                        rho_bar = rho/rho_max
                    else:
                        rho_bar = rho

                    isovalue_features = np.zeros(len(self.isovalue_list))

                    for isovalue_count, isovalue in enumerate(self.isovalue_list):

                        f = rho_bar - isovalue
                        
                        N_x, N_y, N_z = nmb.normal_vector_components(
                            nx, ny, nz, h, f)
                        eisa = nmb.surface_area(
                        nx, ny, nz, N_x, N_y, N_z, x, y, z, h, f, isovalue)
                        
                        isovalue_features[isovalue_count] = eisa

                    isovalue_stat_measure = [np.sum(isovalue_features),
                                             np.mean(isovalue_features),
                                             np.median(isovalue_features),
                                             np.std(isovalue_features),
                                             max(isovalue_features),
                                                            min(isovalue_features)]

                    pair_wise_features[atomic_pair_count,
                                       :] = isovalue_stat_measure

            atomic_pair_count += 1

        final_features_mat = pair_wise_features.reshape(1, num_features)

        
        return final_features_mat

