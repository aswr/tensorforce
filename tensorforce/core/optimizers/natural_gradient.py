# Copyright 2018 Tensorforce Team. All Rights Reserved.
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

import tensorflow as tf

from tensorforce import util
from tensorforce.core import parameter_modules
from tensorforce.core.optimizers import Optimizer
from tensorforce.core.optimizers.solvers import solver_modules


class NaturalGradient(Optimizer):
    """
    Natural gradient optimizer (specification key: `natural_gradient`).

    Args:
        name (string): Module name
            (<span style="color:#0000C0"><b>internal use</b></span>).
        learning_rate (parameter, float >= 0.0): Learning rate as KL-divergence of distributions
            between optimization steps (<span style="color:#C00000"><b>required</b></span>).
        cg_max_iterations (int >= 0): Maximum number of conjugate gradient iterations.
            (<span style="color:#00C000"><b>default</b></span>: 10).
        cg_damping (0.0 <= float <= 1.0): Conjugate gradient damping factor.
            (<span style="color:#00C000"><b>default</b></span>: 1e-3).
        cg_unroll_loop (bool): Whether to unroll the conjugate gradient loop
            (<span style="color:#00C000"><b>default</b></span>: false).
        summary_labels ('all' | iter[string]): Labels of summaries to record
            (<span style="color:#00C000"><b>default</b></span>: inherit value of parent module).
    """

    def __init__(
        self, name, learning_rate, cg_max_iterations=10, cg_damping=1e-3, cg_unroll_loop=False,
        summary_labels=None
    ):
        super().__init__(name=name, summary_labels=summary_labels)

        self.learning_rate = self.add_module(
            name='learning-rate', module=learning_rate, modules=parameter_modules, dtype='float',
            min_value=0.0
        )

        self.solver = self.add_module(
            name='conjugate-gradient', module='conjugate_gradient', modules=solver_modules,
            max_iterations=cg_max_iterations, damping=cg_damping, unroll_loop=cg_unroll_loop
        )

    def tf_step(
        self, variables, arguments, fn_loss, fn_kl_divergence, return_estimated_improvement=False,
        **kwargs
    ):
        # Optimize: argmin(w) loss(w + delta) such that kldiv(P(w) || P(w + delta)) = learning_rate
        # For more details, see our blogpost:
        # https://reinforce.io/blog/end-to-end-computation-graphs-for-reinforcement-learning/

        # Calculates the product x * F of a given vector x with the fisher matrix F.
        # Incorporating the product prevents having to calculate the entire matrix explicitly.
        def fisher_matrix_product(deltas):
            # Gradient is not propagated through solver.
            deltas = [tf.stop_gradient(input=delta) for delta in deltas]

            # kldiv
            kldiv = fn_kl_divergence(**arguments)

            # grad(kldiv)
            kldiv_grads = tf.gradients(ys=kldiv, xs=variables)
            num_grad_none = sum(grad is None for grad in kldiv_grads)
            assert num_grad_none < len(kldiv_grads)
            kldiv_grads = [
                tf.zeros_like(input=var) if grad is None else tf.convert_to_tensor(value=grad)
                for grad, var in zip(kldiv_grads, variables)
            ]

            # delta' * grad(kldiv)
            delta_kldiv_grads = tf.add_n(inputs=[
                tf.reduce_sum(input_tensor=(delta * grad))
                for delta, grad in zip(deltas, kldiv_grads)
            ])

            # [delta' * F] = grad(delta' * grad(kldiv))
            delta_kldiv_grads2 = tf.gradients(ys=delta_kldiv_grads, xs=variables)
            assert sum(grad is None for grad in delta_kldiv_grads2) == num_grad_none
            return [
                tf.zeros_like(input=var) if grad is None else tf.convert_to_tensor(value=grad)
                for grad, var in zip(delta_kldiv_grads2, variables)
            ]

        # loss
        arguments = util.fmap(function=tf.stop_gradient, xs=arguments)
        loss = fn_loss(**arguments)

        # grad(loss)
        loss_gradients = tf.gradients(ys=loss, xs=variables)

        # Solve the following system for delta' via the conjugate gradient solver.
        # [delta' * F] * delta' = -grad(loss)
        # --> delta'  (= lambda * delta)
        deltas = self.solver.solve(
            fn_x=fisher_matrix_product, x_init=None, b=[-grad for grad in loss_gradients]
        )

        # delta' * F
        delta_fisher_matrix_product = fisher_matrix_product(deltas=deltas)

        # c' = 0.5 * delta' * F * delta'  (= lambda * c)
        # TODO: Why constant and hence KL-divergence sometimes negative?
        half = tf.constant(value=0.5, dtype=util.tf_dtype(dtype='float'))
        constant = half * tf.add_n(inputs=[
            tf.reduce_sum(input_tensor=(delta_F * delta))
            for delta_F, delta in zip(delta_fisher_matrix_product, deltas)
        ])

        learning_rate = self.learning_rate.value()

        # Zero step if constant <= 0
        def no_step():
            zero_deltas = [tf.zeros_like(input=delta) for delta in deltas]
            if return_estimated_improvement:
                return zero_deltas, tf.constant(value=0.0, dtype=util.tf_dtype(dtype='float'))
            else:
                return zero_deltas

        # Natural gradient step if constant > 0
        def apply_step():
            # lambda = sqrt(c' / c)
            lagrange_multiplier = tf.sqrt(x=(constant / learning_rate))

            # delta = delta' / lambda
            estimated_deltas = [delta / lagrange_multiplier for delta in deltas]

            # improvement = grad(loss) * delta  (= loss_new - loss_old)
            estimated_improvement = tf.add_n(inputs=[
                tf.reduce_sum(input_tensor=(grad * delta))
                for grad, delta in zip(loss_gradients, estimated_deltas)
            ])

            # Apply natural gradient improvement.
            applied = self.apply_step(variables=variables, deltas=estimated_deltas)

            with tf.control_dependencies(control_inputs=(applied,)):
                # Trivial operation to enforce control dependency
                estimated_delta = util.fmap(function=util.identity_operation, xs=estimated_deltas)
                if return_estimated_improvement:
                    return estimated_delta, estimated_improvement
                else:
                    return estimated_delta

        # Natural gradient step only works if constant > 0
        skip_step = constant > tf.constant(value=0.0, dtype=util.tf_dtype(dtype='float'))
        return self.cond(pred=skip_step, true_fn=no_step, false_fn=apply_step)
