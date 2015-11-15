import numpy as np
import tables as tb
import os
from scipy.io import wavfile
from scipy import signal
from get_heartrates import check_cache, write_cache
from keras.utils.io_utils import HDF5Matrix

import matplotlib.pyplot as plt
import pylab
import re
import random
import code
import errno
import subprocess as sp

"""
Change this according to your local settings
"""
FFMPEG_BIN = "ffmpeg.exe"
HEART_AV_ROOT = "C:\\Uni\\HeartAV"


VIDEO_ROOT = os.path.join(HEART_AV_ROOT, "SensorData", "HeartAV_VideoFiles")

#TODOs: -make ffmpeg subprocces optionaly nonverbose
#       -add a progress bar(generic_utils.ProgBar) when refressing cache
#       -make everything cleaner

class SubjectWav:
    def __init__(self, wav_file):
        self.wav_file = wav_file
        self.sample_rate = None
    def __load_data__(self):
        if self.sample_rate is None:
            fs, frames = wavfile.read(self.wav_file)
            self.sample_rate = fs
            #to mono
            self.audio_data = np.average(frames, axis=1)
    def get_spectrogram(self, at_second, for_seconds=4, window_length=0.05, max_freqency=4000):
        """
            Gets the spectrogram for the file. With window_length in seconds and
            0-max_freqency Hz range. The shorter the window_length the smaller
            freqency resolution
        """
        self.__load_data__()
        at_second = int(at_second)
        fs = self.sample_rate #max_freqency * 2
        nfft = int(fs*window_length)
        noverlap = nfft/ 2
        window_start = at_second * self.sample_rate
        window_size = for_seconds * self.sample_rate
#       code.interact(local=locals())
        f, t, Sxx = signal.spectrogram(self.audio_data[window_start:window_start + window_size],
                      fs,
                      nperseg = nfft, #self.freqency_resolution,
                      noverlap = noverlap,
                      nfft = nfft
                      )
                #to decibel
        max_freq_idx = int((max_freqency / f[-1]) * Sxx.shape[0])
        return f[0:max_freq_idx], t, 20.*np.log10(np.abs(Sxx[0:max_freq_idx])/10e-6)


class SubjectVideo(SubjectWav):
    def __init__(self, avi_file):
        self.avi_file = avi_file
        self.sample_rate = None
    def __load_data__(self):
        if self.sample_rate is None:
            self.sample_rate = 44100
            command = [ FFMPEG_BIN,
                    '-i', self.avi_file,
                    '-ab', '160k',
                    '-ar', str(self.sample_rate), # ouput will have 44100 Hz
                    '-ac', '1', # stereo (set to '1' for mono)
                    '-f', 'wav',
                    '-']
            pipe = sp.Popen(command, stdout=sp.PIPE, bufsize=10**8)
            self.audio_data = np.fromstring(pipe.stdout.read(),dtype="int16")

def plotSubjectWav(sw, at_second,for_seconds=4,):
    f, t, Sxx = sw.get_spectrogram(at_second,for_seconds)
    plt.pcolormesh(t, f, Sxx)
    plt.ylabel('Frequency [Hz]')
    plt.xlabel('Time [sec]')
    plt.show()

"""
    itearates through all wav files, executing func and passing it the path to wav file
"""
def iterateThroughWav():
    for wav in os.listdir(VIDEO_ROOT):
        if wav.endswith(".wav"):
            full_path = VIDEO_ROOT + "\\" + wav
            yield full_path

def maybe_get_unique_avi_from_subjectState_id(ss_id):
    candidates = []
    for f in os.listdir(VIDEO_ROOT):
        if f.endswith(".avi") and ss_id in f:
            candidates += [VIDEO_ROOT + "\\" + f]
    if len(candidates) == 1:
        return candidates[0]
    else:
        return None

FULL_SPECTROGRAM_CACHE = "all_spectrograms.h5"

"""

Returns the spectrograms of interesting region (defined by data)
        from the video files in HEART_AV database

This is the function you probably WANT TO CALL

Assumes 4 second window.

Caches it's results in FULL_SPECTROGRAM_CACHE file, delete that file
to refresh the cache. The data is in different order if the cache is updated
but in the same order if it is not.

Refreshing the cache takes a while and needs ffmpeg. If you have the cache file
from somehwere else, then you can just place it in same dir as this file
and this function should work

Can run several hours if updating cache, otherwise it should take no time

Result is not a numpy array, but does have similar interface. When working with
keras the interface usually isn't similar enough, so should be converted to
numpy array. The returned X_train can be larger then your memory, so be careful
when converting it to numpy arrays

returns: (X_train, Y_train), (X_test), (Y_test)
arguemnts:
    data - a dictonary of subject_state_id to an array of description, timestamp,
            bpm, describing the regions of interest for that subject state id
    train_split = split between train and test data
"""
def full_bpm_to_data(data, train_split=0.9):
    try:
        return readh5File(FULL_SPECTROGRAM_CACHE)
    except IOError:
        pass
    prevElem = None
    h5file = tb.openFile(FULL_SPECTROGRAM_CACHE, mode='w', title="All the data")
    root = h5file.root
    first = True
    X_train = None
    Y_train = None
    X_test = None
    Y_test = None
    for ss_id, regions_of_interest in data.items():
        avi = maybe_get_unique_avi_from_subjectState_id(ss_id)
        if avi:
            sw = SubjectVideo(avi)
            for _,timestamp,bpm in regions_of_interest:
                #reduces the memory used
             #   if random.uniform(0,1) < 0.9:
             #       continue
                timestamp = int(timestamp)
                bpm = round(float(bpm))
                try:
                    _,_,Sxx0 = sw.get_spectrogram(timestamp,4)
                #workaround this error
                #    max_freq_idx = int((max_freqency / f[-1]) * Sxx.shape[0])
                #IndexError: index -1 is out of bounds for axis 0 with size 0
                except IndexError:
                    print("Something went wrong for avi, timestamp ", avi, timestamp)
                    continue
                elem = np.array([Sxx0])
                if prevElem is not None and elem.shape != prevElem.shape:
                    print("skipping " + str(avi) + " " + ss_id +
                            " due to incorrect shape")
                    continue
                prevElem = elem
                #store the elem to disk
                if first:
                    first = False
                    a = tb.Atom.from_dtype(np.dtype('Float32'))
                    data_shape = tuple([0] + list(elem.shape))
                    X_train = h5file.create_earray(root,'X_train',a,data_shape ,"X_train")
                    X_test = h5file.create_earray(root,'X_test',a, data_shape,"X_test")
                    Y_train = h5file.create_earray(root,'Y_train',tb.IntAtom(), (0,),"Y_train")
                    Y_test = h5file.create_earray(root,'Y_test',tb.IntAtom(), (0,),"Y_test")
                if random.uniform(0,1) < train_split:
                    X_train.append(np.array([elem]))
                    Y_train.append([bpm])
                else:
                    X_test.append(np.array([elem]))
                    Y_test.append([bpm])
            h5file.flush()
            print("converted " + str(avi))
        else:
            print("Skipping " + ss_id + " becuase it isn't unique")
    h5file.close()
    return readh5File(FULL_SPECTROGRAM_CACHE)

SPECTROGRAM_CACHE = "spectrograms.h5"
def bpm_to_data(data, train_split=0.9):
    try:
        return readh5File(SPECTROGRAM_CACHE)
    except IOError:
        pass
    pattern = re.compile(".*vp_(\\d+)_(\\d+)_.*")
    prevElem = None
   # limit = 250
    h5file = tb.openFile(SPECTROGRAM_CACHE, mode='w', title="All the data")
    root = h5file.root
    first = True
    X_train = None
    Y_train = None
    X_test = None
    Y_test = None

    for wavFile in iterateThroughWav():
        m = pattern.match(wavFile)
        subjectId = int(m.group(1))
        stateId = int(m.group(2))
        sw = SubjectWav(wavFile)
        subjectStateId = str(subjectId) + "_" + str(stateId).zfill(2)
        try:
            for _,timestamp,bpm in data[subjectStateId]:
                #reduces the memory used
             #   if random.uniform(0,1) < 0.9:
             #       continue
                timestamp = int(timestamp)
                bpm = round(float(bpm))
                _,_,Sxx0 = sw.get_spectrogram(timestamp,4)
               # print(Sxx0.shape) #(651,154) (801,219)
                elem = np.array([Sxx0])
                if prevElem is not None and elem.shape != prevElem.shape:
                    print("skipping " + str(wavFile) + " " + subjectStateId +
                            " due to incorrect shape")
                    continue
                prevElem = elem
                #store the elem to disk
                if first:
                    first = False
                    a = tb.Atom.from_dtype(np.dtype('Float32'))
                    data_shape = tuple([0] + list(elem.shape))
                    X_train = h5file.create_earray(root,'X_train',a,data_shape ,"X_train")
                    X_test = h5file.create_earray(root,'X_test',a, data_shape,"X_test")
                    Y_train = h5file.create_earray(root,'Y_train',tb.IntAtom(), (0,),"Y_train")
               #     code.interact(local=locals())
                    Y_test = h5file.create_earray(root,'Y_test',tb.IntAtom(), (0,),"Y_test")
                if random.uniform(0,1) < 0.9:
                    X_train.append(np.array([elem]))
                    Y_train.append([bpm])
                else:
                    X_test.append(np.array([elem]))
                    Y_test.append([bpm])
            h5file.flush()
        except KeyError:
            print("can not find: " + subjectStateId + ".")
            pass
        print("converted " + str(wavFile))
    #Could not broadcast error means that not all elemnt of X_train have the same shape
    #usually meaning there is something wrong with files
    h5file.close()
#    data = (X_train, Y_train) , (X_test, Y_test)
#    write_cache(SPECTROGRAM_CACHE,data)
    return readh5File(SPECTROGRAM_CACHE)
def appendToDatasetAt(dataset,idx, obj):
    if not dataset.shape[0] < idx:
        dataset.resize(idx + 1000,axis=0)
        print("resizing")
    dataset[0] = obj

def readh5File(h5file):
    h5file = tb.openFile(h5file, mode='r', title="All the data")
    return ((h5file.root.X_train , h5file.root.Y_train),
            (h5file.root.X_test, h5file.root.Y_test))

def make_sure_path_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


if __name__ == "__main__":
    sw = None
    for p in iterateThroughWav():
        v = p.replace(".wav",".avi")
        print(v)
        sw = SubjectVideo(v)
    plotSubjectWav(sw, 31*60+17)

# make_sure_path_exists("dat")
#                filename = os.path.join("dat", subjectStateId + "_" + str(timestamp))
#                memmap_elem = np.memmap(filename,dtype='float32',mode='w+', shape=(elem.shape))
#                memmap_elem[:] = elem[:]
#                del memmap_elem #flushes to disk
#                #make a ro version of it that goes into the list
#                ro_elem = np.memmap(filename,dtype='float32',mode='r', shape=elem.shape)
#
