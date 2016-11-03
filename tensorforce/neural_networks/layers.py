# Copyright 2016 reinforce.io. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""
Creates various neural network layers. For most layers, these functions use
TF-slim layer types. The purpose of this class is to encapsulate
layer types to mix between layers available in TF-slim and custom implementations.
"""

import tensorflow as tf
from tensorforce.util.config_util import get_function

tf_slim = tf.contrib.slim


def dense(input_handle, config, scope):
    """
    Fully connected layer.

    :param config: Layer config
    :param input: Input to the layer, e.g. handle to another layer
    :param scope: Layer name
    :return:
    """
    kwargs = {
        'weights_initializer': get_function(config['weight_init'], config['weight_init_param']),
        'biases_initializer': get_function(config['bias_init'], config['bias_init_param']),
        'activation_fn': get_function(config['activation'], config['activation_param']),
        'weights_regularizer': get_function(config['regularization'], config['regularization_param']),
    }
    return tf_slim.fully_connected(input_handle,
                                   config['neurons'],
                                   scope=scope,
                                   **kwargs)


def conv2d(input_handle, config, scope):
    """
    Convolutional 2d layer.

    :param config: Layer config
    :param input: Input to the layer, e.g. handle to another layer
    :param scope: Layer name
    :return:
    """
    kwargs = {
        'weights_initializer': get_function(config['weight_init'], config['weight_init_param']),
        'biases_initializer': get_function(config['bias_init'], config['bias_init_param']),
        'activation_fn': get_function(config['activation'], config['activation_param']),
        'weights_regularizer': get_function(config['regularization'], config['regularization_param']),
    }
    return tf_slim.conv2d(input_handle,
                          config['neurons'],
                          config['conv_filter_shape'],
                          scope=scope,
                          **kwargs)


layers = {
    'dense': dense,
    'conv2d': conv2d
}
