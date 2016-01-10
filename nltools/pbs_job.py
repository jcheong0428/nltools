# Sam Greydanus and Luke Chang 2015

import os

import time
import sys
import warnings
from distutils.version import LooseVersion
import random

import cPickle 
import numpy as np
import matplotlib.pyplot as plt
from nilearn import datasets
from nilearn import plotting

import nibabel as nib

import sklearn
from sklearn import neighbors
from sklearn.externals.joblib import Parallel, delayed, cpu_count
from sklearn import svm
from sklearn.cross_validation import cross_val_score
from sklearn.base import BaseEstimator
from sklearn import neighbors
from sklearn.svm import SVR

from nilearn import masking
from nilearn.input_data import NiftiMasker

from nltools.analysis import Predict
import glob

class PBS_Job:
    def __init__(self, bdata, y, core_out_dir = None, brain_mask=None, process_mask=None, radius=4, kwargs=None): #no scoring param
        
        self.bdata = bdata
        self.y = np.array(y)
        self.data_dir = os.path.join(os.getcwd(),'/resources')

        #set up core_out_dir
        if core_out_dir is None:
            os.system("mkdir core_out_dir")
            self.core_out_dir = os.path.join(os.getcwd(),'core_out_dir')
        else:
            self.core_out_dir = core_out_dir
        
        #set up brain_mask
        if type(brain_mask) is str:
            brain_mask = nib.load(brain_mask)
        elif brain_mask is None:
            brain_mask = nib.load(os.path.join(self.data_dir,'MNI152_T1_2mm_brain_mask_dil.nii.gz'))
        elif type(brain_mask) is not nib.nifti1.Nifti1Image:
            print(brain_mask)
            print(type(brain_mask))
            raise ValueError("brain_mask is not a nibabel instance")
        self.brain_mask = brain_mask
        
        #set up process_mask
        if type(process_mask) is str:
            process_mask = nib.load(process_mask)
        elif process_mask is None:
            process_mask = nib.load(os.path.join(self.data_dir,"FSL_RIns_thr0.nii.gz"))
        elif type(brain_mask) is not nib.nifti1.Nifti1Image:
            print(process_mask)
            print(type(process_mask))
            raise ValueError("process_mask is not a nibabel instance")
        self.process_mask = process_mask
        
        #set up other parameters
        self.radius = radius
        self.nifti_masker = NiftiMasker(mask_img=self.brain_mask)

    def make_startup_script(fn):
        with open(os.path.join(os.getcwd(), fn), "w") as f:
            f.write("from nltools.pbs_job import PBS_Job \n\
import cPickle \n\
import os \n\
import sys \n\
pdir = \"" + os.path.join(os.getcwd(),'pbs_searchlight.pkl') + "\" \n\
parallel_job = cPickle.load( open(pdir) ) \n\
core_i = int(sys.argv[1]) \n\
ncores = int(sys.argv[2]) \n\
parallel_job.run_core(core_i, ncores) ")
      
    def make_pbs_email_alert(self, email):
        title  = "email_alert.pbs"
        with open(os.path.join(os.getcwd(), title), "w") as f:
            f.write("#PBS -m ea \n\
#PBS -N email_alert \n\
#PBS -M " + email + " \n\
exit 0")

    def make_pbs_scripts(self, script_name, core_i, ncores, walltime):
        with open(os.path.join(os.getcwd(), script_name), "w") as f:
            f.write("#!/bin/bash -l \n\
# declare a job name \n\
#PBS -N sl_core_" + str(core_i) + " \n\
# request a queue \n\
#PBS -q default \n\
# request 1 core \n\
#PBS -l cores=1:ppn=1 \n\
# request wall time (default is 1 hr if not set)\n\
#PBS -l walltime=" + walltime + " \n\
# execute core-level code in same directory as head core \n\
cd " + os.getcwd() + " \n\
# run a startup python script \n\
python icore_startup.py " + str(core_i) + " " + str(n_cores) + " \n\
exit 0" )

    def run_core(self, core_i, ncores):
        tic = time.time()
        self.errf("Started run_core", core_i = core_i, dt = (time.time() - tic))

        core_groups = [] #a list of lists of indices
        for i in range(0,ncores):
            start_i = i*self.A.shape[0] / ncores
            stop_i = (i+1)*A.shape[0] / ncores
            core_groups.append( range(start_i, stop_i) )

        runs_per_core = len(core_groups[core_i])
        runs_total = A.shape[0]
        self.errf("Started run_core", core_i = core_i, time = (time.time() - tic))
        Searchlight.errf("This core will be doing " + str(runs_per_core) + " runs out of " \
             + str(runs_total) + " total.", core_i=core_i, dt=(time.time() - tic))

        #clear data in r_all and weights files, if any
        rf = os.path.join(self.core_out_dir, "r_all" + str(core_i) + '.txt') #correlation file
        wf = os.path.join(self.core_out_dir, "weights" + str(core_i) + '.txt') # weight file
        pf = os.path.join(self.core_out_dir, "progress.txt") # progress file
        with open(rf, 'w') as r_file, open(wf, 'w') as w_file, open(pf, 'w') as p_file:
            r_file.seek(0), w_file.seek(0), p_file.seek(0)
            r_file.truncate(), w_file.truncate(), p_file.truncate()

        self.errf("Begin main loop", core_i = core_i, time = (time.time() - tic))
        t0 = time.time()
        for i in range( core_groups ):
            tic = time.time()
            searchlight_sphere = A[core_groups[core_i][i]][:].toarray() #1D vector
            searchlight_mask = self.nifti_masker.inverse_transform( searchlight_sphere )

            #apply the Predict method

            model = Predict(self.bdata, self.y, \
                    mask = searchlight_mask, \
                    algorithm=self.kwargs['algorithm'], \
                    output_dir=core_out_dir, \
                    cv_dict = self.kwargs['cv_dict'], \
                    **self.kwargs['predict_kwargs'])
            model.predict(save_plot=False)
            
            #save r correlation values
            with open(os.path.join(self.core_out_dir, "r_all" + str(core_i) + ".txt"), "a") as f:
                r = model.r_xval
                if r != r: r=0.0
                if i + 1 == runs_per_core:
                    f.write(str(r)) #if it's the last entry, don't add a comma at the end
                else:
                    f.write(str(r) + ",")

            #save weights
            with open(os.path.join(self.output_dir, "weights" + str(core_i) + ".txt"), "a") as f:
                if i + 1 < runs_per_core:
                    l = model.predictor.coef_.squeeze()
                    for j in range(len(l) - 1):
                        f.write(str(l[j]) + ',')
                    f.write( str(l[j]) +  "\n") #if it's the last entry, don't add a comma at the end
                else:
                    l = model.predictor.coef_.squeeze()
                    for j in range(len(l) - 1):
                        f.write(str(l[j]) + ',')
                    f.write( str(l[j])) #if it's the last entry, don't add a comma or a \n at the end

            #periodically update estimate of processing rate
            if i%7 == 0:
                self.estimate_rate(core_i, (time.time() - t0), i + 1, core_groups)
                #every so often, clear the file
                if i%21 == 0 and core_i == 0:
                    ratef = os.path.join(os.getcwd(),"rate.txt")
                    with open(ratef, 'w') as f:
                        f.write("") #clear the file
            
        # read the count of the number of cores that have finished
        with open(os.path.join(self.output_dir,"progress.txt"), 'r') as f:
            cores_finished = f.readline()

        # if all cores are finished, run a clean up method
        # otherwise, increment number of finished cores and terminate process
        with open(os.path.join(self.output_dir,"progress.txt"), 'w') as f:
            if (len(cores_finished) > 0):
                f.write( str(int(cores_finished) + 1) )
                if (int(cores_finished) + 2 >= ncores):
                    f.seek(0)
                    f.truncate()
                    self.clean_up( email_flag = True)
            else:
                f.write( "0" )

    def errf(self, text, core_i = None, dt = None):
        if core_i is None or core_i == 0:
            with open(os.path.join(os.getcwd(),'errf.txt'), 'a') as f:
                f.write(text + "\n")
                if dt is not None:
                    f.write("       ->Time: " + str(dt) + " seconds")

    def get_t_remaining(self, rate, jobs, core_groups):
        t = int(rate*(core_groups-jobs))
        t_day = t / (60*60*24)
        t -= t_day*60*60*24
        t_hr = t / (60*60)
        t -= t_hr*60*60
        t_min = t / (60)
        t -= t_min*60
        t_sec = t
        return str(t_day) + "d" + str(t_hr) + "h" + str(t_min) + "m" + str(t_sec) + "s"

    def estimate_rate(self, core, tdif, jobs, core_groups):
        ratef = os.path.join(os.getcwd(),"rate.txt")
        if not os.path.isfile(ratef):
            with open(ratef, 'w') as f:
                f.write("")

        maxrate = ''
        prevtime = ''
        with open(ratef, 'r') as f:
            maxrate = f.readline().strip('\n')
            prevtime = f.readline().strip('\n')
            coreid = f.readline().strip('\n')
            est = f.readline().strip('\n')

        with open(ratef, 'w') as f:
            if (len(maxrate) > 0):
                if (float(maxrate) < tdif/jobs):
                    est = self.get_t_remaining(tdif/jobs, jobs, core_groups)
                    f.write(str(tdif/jobs) + "\n" + str(time.time()) + "\nCore " + \
                        str(core) + " is slowest: " + str(tdif/jobs) + " seconds/job\n" + \
                        "This run will finish in " + est + "\n")
                else:
                    f.write(maxrate + "\n" + prevtime + "\n" + coreid + "\n" + est + "\n")
            elif (len(prevtime) == 0):
                est = self.get_t_remaining(tdif/jobs, jobs, core_groups)
                f.write(str(tdif/jobs) + "\n" + str(time.time()) + "\nCore " + str(core) + \
                    " is slowest: " + str(tdif/jobs) + " seconds/job\n" + "This run will finish in " \
                    + est + "\n")
        
    # helper function which finds the indices of each searchlight and returns a lil file
    def make_searchlight_masks(self):
        # Compute world coordinates of all in-mask voxels.
        # Return indices as sparse matrix of 0's and 1's
        print("start get coords")
        world_process_mask = self.nifti_masker.fit_transform(self.process_mask)
        world_brain_mask = self.nifti_masker.fit_transform(self.brain_mask)
        
        process_mask_1D = world_brain_mask.copy()
        process_mask_1D[:,:] = 0
        no_overlap = np.where( world_process_mask * world_brain_mask > 0 ) #get the indices where at least one entry is 0
        process_mask_1D[no_overlap] = 1 #delete entries for which there is no overlap
        
        mask, mask_affine = masking._load_mask_img(self.brain_mask)
        mask_coords = np.where(mask != 0)
        mc1 = np.reshape(mask_coords[0], (1, -1))
        mc2 = np.reshape(mask_coords[1], (1, -1))
        mc3 = np.reshape(mask_coords[2], (1, -1))
        mask_coords = np.concatenate((mc1.T,mc2.T, mc3.T), axis = 1)
        
        selected_3D = self.nifti_masker.inverse_transform( process_mask_1D )
        process_mask_coords = np.where(selected_3D.get_data()[:,:,:,0] != 0)
        pmc1 = np.reshape(process_mask_coords[0], (1, -1))
        pmc2 = np.reshape(process_mask_coords[1], (1, -1))
        pmc3 = np.reshape(process_mask_coords[2], (1, -1))
        process_mask_coords = np.concatenate((pmc1.T,pmc2.T, pmc3.T), axis = 1)
        
        clf = neighbors.NearestNeighbors(radius = self.radius)
        A = clf.fit(mask_coords).radius_neighbors_graph(process_mask_coords)
        del mask_coords, process_mask_coords, selected_3D, no_overlap
        
        print("Built searchlight masks./nEach searchlight has on the order of " + str( sum(sum(A[0].toarray())) ) + " voxels")

        self.A = A.tolil()
        self.process_mask_1D = self.process_mask_1D
            
    def clean_up(self, email_flag = True):
        #clear data in reassembled and weights files, if any

                #clear data in r_all and weights files, if any
        rf = os.path.join(self.os.getcwd(), "correlations.txt") # correlation file (for combined nodes)
        wf = os.path.join(self.os.getcwd(), "weights.txt") # weight file (for combined nodes)
        with open(rf, 'w') as r_combo, open(wf, 'w') as w_combo:
            r_combo.seek(0), w_combo.seek(0)
            r_combo.truncate(), w_combo.truncate()

        #get name and location of each core's correlation, weights file
        core_i = 0
        r_prefix, w_prefix, = "r_all", "weights"
        r_core_data = os.path.join(self.core_out_dir, r_prefix + str(core_i) + ".txt")
        w_core_data = os.path.join(self.core_out_dir, w_prefix + str(core_i) + ".txt")

        data_was_merged = False
        print( "Merging data to one file" )
        #write results from all cores to one text file in a csv format
        while (os.path.isfile(r_core_data) and os.path.isfile(w_core_data)):
            with open (r_core_data, "r") as r_core, open (w_core_data, "r") as w_core:
                rdata = r_core.read() ; weights = w_core.read()

                with open(rf, "a") as r_combo, open(wf, "a") as w_combo:
                    r_combo.write(rdata + ','), w_combo.write(weights + '\n')

            core_i += 1
            r_core_data = os.path.join(self.core_out_dir, r_prefix + str(core_i) + ".txt")
            w_core_data = os.path.join(self.core_out_dir, w_prefix + str(core_i) + ".txt")

            data_was_merged = True

        #remove the last comma in the csv file we just generated
        if (data_was_merged):
            with open(rf, 'rb+') as r_combo, open(wf, 'rb+') as w_combo:
                r_combo.seek(-1, os.SEEK_END), w_combo.seek(-1, os.SEEK_END)
                r_combo.truncate(), w_combo.truncate()

            #get data from combo file and convert it to a .nii file
            self.reconstruct(rf)
        else:
            print("ERROR: data not merged correctly (in directory: " + os.getcwd() + ")")

        print( "Finished reassembly (reassembled " + str(core_i) + " items)" )

        #send user an alert email  alert by executing a blank script with an email alert tag
        if email_flag:
            os.system("qsub email_alert.pbs")

        # os.system("rm pbs_searchlight.pickle")
        print("Cleaning up...")
        os.system("rm email_alert*")
        os.system("rm *searchlight_* *div* *errf* *rate*")
        os.system("rm inner_searchlight_script*")

    def reconstruct(self, rf):
            #open the reassembled correlation data and build a python list of float type numbers
            with open(rf, 'r') as r_combo:
                rdata = np.fromstring(r_combo.read(), dtype=float, sep=',')

            #find coords of all values in process mask that are equal to 1
            coords = np.where(self.process_mask_1D == 1)[1]

            #in all the locations that are equal to 1, store the correlation data
            #   (coords and data should have same length)
            self.process_mask_1D[0][coords] = rdata

            #transform rdata to 3D "correlation heat map" (nifti format)
            rdata_3D = self.nifti_masker.inverse_transform( self.process_mask_1D )
            rdata_3D.to_filename(os.path.join(os.getcwd(),'rdata_3D.nii.gz')) #save nifti image
            # os.system("rm correlations.txt")