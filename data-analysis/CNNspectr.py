from spectrogram import bpm_to_data
from get_heartrates import get_interesting_heartrates
from convertToWav import VIDEO_ROOT
from keras.models import Sequential
from keras.layers.core import Dense, Activation, Dropout, Flatten
from keras.layers.convolutional import Convolution2D, MaxPooling2D
from keras.optimizers import SGD
from keras.utils import np_utils, generic_utils

import random
import numpy as np
import code
#dumy_data_subject1 = [(i*5 + 1, random.randint(lowest_bpm, highest_bpm)) for i in range(1,200)]
#dumy_data = {35 : dumy_data_subject1}

(X_train, y_train), (X_test, y_test) = bpm_to_data(get_interesting_heartrates("C:\\Uni\\HeartAV"))

lowest_bpm = min(min(y_train) , min(y_test))
highest_bpm = max(max(y_train) , max(y_test))
scale = 1
nb_classes = (highest_bpm - lowest_bpm + 1*scale) // scale



print(highest_bpm, lowest_bpm, nb_classes)

#code.interact(local=locals())
y_train = list(map(lambda x : (x - lowest_bpm)//scale, y_train))
y_test = list(map(lambda x : (x - lowest_bpm) //scale, y_test))
# convert class vectors to binary class matrices
# converts a number to unary so 4 is 0001
Y_train = np_utils.to_categorical(y_train, nb_classes)
Y_test = np_utils.to_categorical(y_test, nb_classes)

print(X_train[0].shape)
#X_train = np.array(X_train)
#X_test = np.array(X_test)

nb_filters = 10
nb_pool = 2
nb_rows = 4
nb_coloumns = 4

model = Sequential()

model.add(Convolution2D(nb_filters,nb_rows,nb_coloumns, input_shape=(X_train[0].shape)))
model.add(Activation('relu'))

model.add(MaxPooling2D(pool_size=(nb_pool*2, nb_pool)))

model.add(Convolution2D(nb_filters,nb_rows,nb_coloumns))
model.add(Activation('relu'))

model.add(MaxPooling2D(pool_size=(nb_pool, nb_pool)))

model.add(Convolution2D(nb_filters*2, nb_rows,nb_coloumns))
model.add(Activation('relu'))

model.add(MaxPooling2D(pool_size=(nb_pool, nb_pool)))
model.add(Dropout(0.2))


model.add(Flatten())
model.add(Dense(150))
model.add(Activation('relu'))
model.add(Dropout(0.5))
model.add(Dense(nb_classes))
model.add(Activation('softmax'))

model.compile(loss='binary_crossentropy', optimizer='adadelta')

#model.fit(X_train, Y_train, batch_size=50, nb_epoch=30, show_accuracy=True, verbose=1, validation_data=(X_test, Y_test))

nb_epoch = 30
train_size =  X_train.shape[0]
batch_size = 50
batchLimits = [(i*batch_size, i*batch_size+batch_size) for i in range(0, train_size//batch_size)]
batchLimits += [((train_size//batch_size)*batch_size + 1,  train_size)]

print("Training on " + str(train_size) + " examples")
X_test = np.array(X_test)
for e in range(nb_epoch):
        random.shuffle(batchLimits)
        print('-'*40)
        print('Epoch', e)
        print('-'*40)
        print("Training...")
        # batch train with realtime data augmentation
        progbar = generic_utils.Progbar(train_size - 1, verbose=1)
        for (start, end) in batchLimits:
            X_batch = np.empty([end - start] + list(X_train.shape[1:]))
            X_batch[:] = X_train[start:end]
            loss, accuracy = model.train_on_batch(X_batch, Y_train[start:end], accuracy=True)
            progbar.add(X_batch.shape[0], values=[("train loss", loss), ("accuracy", accuracy)])

#        print("Testing...")
#        score, accuracy = model.test_on_batch(X_test, Y_test, accuracy=True)
#        print("  Testing score: " + str(score) + " accuracy: " + str(accuracy))

score = model.evaluate(X_test, Y_test, show_accuracy=True, verbose=0)
print('Test score:', score[0])
print('Test accuracy:', score[1])
