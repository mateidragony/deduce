# Binary Trees with In-order Iterators (Part 2)

This is the sixth blog post in a
[series](https://siek.blogspot.com/2024/06/data-structures-and-algorithms-correctly.html)
about developing correct implementations of basic data structures and
algorithms using the [Deduce](https://github.com/jsiek/deduce)
language and proof checker. 

This post continues were we left off from the
[previous post](https://siek.blogspot.com/2024/07/binary-trees-with-in-order-iterators.html) 
in which we implemented binary trees and in-order tree iterators.

Our goal in this post is to prove that we correctly implemented the
iterator operations:

```
ti2tree : < E > fn TreeIter<E> -> Tree<E>
ti_first : < E > fn Tree<E>,E,Tree<E> -> TreeIter<E>
ti_get : < E > fn TreeIter<E> -> E
ti_next : < E > fn TreeIter<E> -> TreeIter<E>
ti_index : < E > fn(TreeIter<E>) -> Nat
```

The first operation, `ti2tree`, requires us to first obtain a tree
iterator, for example, with `ti_first`, so `ti2tree` does not have a
correctness criteria all of its own, but instead the proof of its
correctness will be part of the correctness of the other operations.

So we skip to the proof of correctness for `ti_first`.

## Correctness of `ti_first`

Let us recall and make explicit the specification of `ti_first`:

**Specification:** The `ti_first(A, x, B)` function returns an
iterator pointing to the first node with respect to in-order
traversal, of the tree `TreeNode(A, x, B)`.

Also, recall that we said the following about `ti2tree` and
`ti_first`: creating an iterator from a tree using `ti_first` and then
applying `ti2tree` produces the original tree.

So we have two properties to prove about `ti_first`. For the first
property, we need a way to formalize &quot;the first node with respect
to in-order traversal&quot;. This is where the `ti_index` operation
comes in. If `ti_first` returns the first node, then its index should
be `0`. So we have the following theorem:

```
theorem ti_first_index: all E:type, A:Tree<E>, x:E, B:Tree<E>.
  ti_index(ti_first(A, x, B)) = 0
proof
  arbitrary E:type, A:Tree<E>, x:E, B:Tree<E>
  definition ti_first
  ?
end
```

After expanding the definition of `ti_first`, we are left with the
following goal. So we need to prove a lemma about the `first_path`
auxiliary function.

```
	ti_index(first_path(A,x,B,empty)) = 0
```

Here is a first attempt to formulate the lemma.

```
lemma first_path_index: all E:type. all A:Tree<E>. all y:E, B:Tree<E>.
  ti_index(first_path(A,y,B, empty)) = 0
```

However, because `first_path` is recursive, we will need to prove this
by recursion on `A`. But looking at the second clause of in the
definition of `first_path`, the `path` argument grows, so our
induction hypothesis, which requires the `path` argument to be empty,
will not be applicable. As is often the case, we need to generalize
the lemma. Let's replace `empty` with an arbitrary `path` as follows.

```
lemma first_path_index: all E:type. all A:Tree<E>. all y:E, B:Tree<E>, path:List<Direction<E>>.
  ti_index(first_path(A,y,B, path)) = 0
```

But now this lemma is false. Consider the following situation in which
the current node `y` is `5` and the `path` is `L,R` (going from node
`5` up to node `3`).

![Diagram for lemma first path index](./first_path1.png)

The index of node `5` is not `0`, it is `5`! Instead the index of node
`5` is equal to the number of nodes that come before `5` according to
in-order travesal. We can obtain that portion of the tree using
functions that we have already defined, in particular `take_path`
followed by `plug_tree`. So we can formulate the lemma as follows.

```
lemma first_path_index: all E:type. all A:Tree<E>. all y:E, B:Tree<E>, path:List<Direction<E>>.
  ti_index(first_path(A,y,B, path)) = num_nodes(plug_tree(take_path(path), EmptyTree))
proof
  arbitrary E:type
  induction Tree<E>
  case EmptyTree {
    arbitrary y:E, B:Tree<E>, path:List<Direction<E>>
    ?
  }
  case TreeNode(L, x, R) suppose IH {
    arbitrary y:E, B:Tree<E>, path:List<Direction<E>>
    ?
  }
end
```

For the case `A = EmptyTree`, the goal simply follows from the
definitions of `first_path`, `ti_index`, and `ti_take`.

```
    conclude ti_index(first_path(EmptyTree,y,B,path))
           = num_nodes(plug_tree(take_path(path),EmptyTree))
                by definition {first_path, ti_index, ti_take}.
```

For the case `A = TreeNode(L, x, R)`, after expanding the definition
of `first_path`, we need to prove:

```
  ti_index(first_path(L,x,R,node(LeftD(y,B),path)))
= num_nodes(plug_tree(take_path(path),EmptyTree))
```

But that follows from the induction hypothesis and the
definition of `take_path`.

```
    definition {first_path}
    equations
          ti_index(first_path(L,x,R,node(LeftD(y,B),path)))
        = num_nodes(plug_tree(take_path(node(LeftD(y,B),path)),EmptyTree))
                by IH[x, R, node(LeftD(y,B), path)]
    ... = num_nodes(plug_tree(take_path(path),EmptyTree))
                by definition take_path.
```

Here is the completed proof of the `first_path_index` lemma.

```{.deduce #first_path_index}
lemma first_path_index: all E:type. all A:Tree<E>. all y:E, B:Tree<E>, path:List<Direction<E>>.
  ti_index(first_path(A,y,B, path)) = num_nodes(plug_tree(take_path(path), EmptyTree))
proof
  arbitrary E:type
  induction Tree<E>
  case EmptyTree {
    arbitrary y:E, B:Tree<E>, path:List<Direction<E>>
    conclude ti_index(first_path(EmptyTree,y,B,path))
           = num_nodes(plug_tree(take_path(path),EmptyTree))
                by definition {first_path, ti_index, ti_take}.
  }
  case TreeNode(L, x, R) suppose IH {
    arbitrary y:E, B:Tree<E>, path:List<Direction<E>>
    definition {first_path}
    equations
          ti_index(first_path(L,x,R,node(LeftD(y,B),path)))
        = num_nodes(plug_tree(take_path(node(LeftD(y,B),path)),EmptyTree))
                by IH[x, R, node(LeftD(y,B), path)]
    ... = num_nodes(plug_tree(take_path(path),EmptyTree))
                by definition take_path.
  }
end
```

<!--
```{.deduce file=BinaryTreeProof.pf} 
import BinaryTree

<<first_path_index>>

```
-->