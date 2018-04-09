from mygrad.operation_base import Operation, BroadcastableOp
import numpy as np


__all__ = ["GetItem",
           "SetItem"]


class GetItem(Operation):
    """ Defines the __getitem__ interface for a Tensor, supporting back-propagation

        Supports back-propagation through all valid numpy-indexing (basic, advanced, mixed, etc.)"""
    def __call__(self, a, index):
        """ a[index]

            Parameters
            ----------
            a : mygrad.Tensor
                The tensor whose entries are being accessed.

            index : valid-array-index
                An n-dimensional index for specifying entries or subregions of `a`.
                All means of numpy-array indexing (basic, advanced, mixed, etc) are
                supported."""
        self.variables = (a,)
        self.index = index
        out = a.data[index]
        self.shape = out.shape if isinstance(out, np.ndarray) else None
        return out

    def backward_var(self, grad, index, **kwargs):
        a = self.variables[index]
        out = np.zeros_like(a.data)
        np.add.at(out, self.index, grad)
        a.backward(out, **kwargs)


def _arr(*shape):
    """ Construct an array of a specified consisting of values [0, _arr.size)
        filled in row-major order.

        Parameters
        ----------
        *shape : int

        Returns
        -------
        numpy.ndarray"""
    return np.arange(np.prod(shape)).reshape(shape)


def _is_int_array_index(index):
    """ Returns True if `index` contains any array-like integer-valued sequences

        Parameters
        ----------
        index : Tuple[Any]

        Returns
        -------
        bool """
    return any(np.issubdtype(np.asarray(ind).dtype, np.int_) and np.asarray(ind).ndim for ind in index)


def _is_bool_array_index(index):
    """ Returns True if `index` solely contains a boolean-valued array

        Parameters
        ----------
        index : Tuple[Any]

        Returns
        -------
        bool """
    return len(index) == 1 and np.issubdtype(np.asarray(index[0]).dtype, np.bool_)


class SetItem(BroadcastableOp):
    """ Defines the __setitem__ interface for a Tensor, supporting back-propagation through
        both the tensor being set and the tensor whose .

        Supports back-propagation through all valid numpy-indexing (basic, advanced, mixed, etc.),
        as well as """
    def __call__(self, a, b, index):
        """ a[index] = b

            Parameters
            ----------
            a : mygrad.Tensor
                The tensor whose entries are being set

            b : mygrad.Tensor
                `b` must be broadcast-compatible with `a[index]`

            index : valid-array-index
                An n-dimensional index for specifying entries or subregions of `a`.
                All means of numpy-array indexing (basic, advanced, mixed, etc) are
                supported.

            Notes
            -----
            Additional computational overhead is required for back-propagation when
            `index` contains any integer-valued arrays, to accommodate for the scenario
            in which a single element is set multiple times."""
        self.variables = (a, b)

        self.index = index if isinstance(index, tuple) else (index,)
        a.data[index] = b.data

        return a.data

    def backward_var(self, grad, index, **kwargs):
        a, b = self.variables
        if index == 0:
            grad = np.copy(grad)
            grad[self.index] = 0
            kwargs["_broadcastable"] = False
            a.backward(grad, **kwargs)
        elif index == 1:
            grad_sel = np.asarray(grad[self.index])

            # Basic indexing and indexing with a single boolean-array is trivial. The
            # gradient into b can just be accessed by indexing into `grad`.
            # Indexing with integer-valued arrays can be problematic, as the same
            # item can be specified multiple for "setting"; here only the last set-item
            # for that element has an effect. For example:
            #     x[np.array([0, 0])] = np.array([2, 3])  # `3` gets set to x[0]; 2 has no effect
            # Thus only that corresponding element in `grad` (that corresponding to `3`)
            # should be propagated back into b. Thus we must check to see if any items are
            # being set redundantly, and mask out any elements in `grad` corresponding to
            # the elements in `b` that weren't actually set.
            if not np.shares_memory(grad_sel, grad) and grad_sel.size > 0 and grad_sel.ndim > 0:
                if not _is_bool_array_index(self.index) and _is_int_array_index(self.index):
                    # create an array of unique elements, and see if indexing into it produces
                    # any redundant elements
                    unique = _arr(*grad.shape)
                    sub_sel = unique[self.index].flat
                    elements, first_inds, = np.unique(np.flip(sub_sel, axis=0), return_index=True)
                    if len(first_inds) < len(sub_sel):
                        # one or more elements were set redundantly, identify the entries in `b`
                        # that actually were set to those elements (the last-most set-item calls
                        # for those elements) and propagate only the corresponding elements from grad

                        first_inds = (len(sub_sel) - 1) - first_inds
                        mask = np.zeros_like(sub_sel)
                        mask[first_inds] = 1
                        mask = mask.reshape(grad_sel.shape)
                        grad_sel *= mask

            # handle the edge case of "projecting down" on setitem. E.g:
            # x = Tensor([0, 1, 2])
            # y = Tensor([3])
            # x[0] = y  # this is legal since x[0] and y have the same size
            if grad_sel.ndim < b.ndim:
                grad_sel = grad_sel.reshape(b.shape)
            b.backward(grad_sel, **kwargs)
        else:
            raise IndexError
