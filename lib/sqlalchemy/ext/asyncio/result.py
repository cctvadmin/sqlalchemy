# ext/asyncio/result.py
# Copyright (C) 2020-2021 the SQLAlchemy authors and contributors
# <see AUTHORS file>
#
# This module is part of SQLAlchemy and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

import operator

from ... import util
from ...engine.result import _NO_ROW
from ...engine.result import FilterResult
from ...engine.result import FrozenResult
from ...engine.result import MergedResult
from ...util.concurrency import greenlet_spawn

if util.TYPE_CHECKING:
    from typing import Any
    from typing import Int
    from typing import Iterator
    from typing import List
    from typing import Mapping
    from typing import Optional

    from ...engine.result import Row


class AsyncCommon(FilterResult):
    async def close(self):
        """Close this result."""

        await greenlet_spawn(self._real_result.close)


class AsyncResult(AsyncCommon):
    """An asyncio wrapper around a :class:`_result.Result` object.

    The :class:`_asyncio.AsyncResult` only applies to statement executions that
    use a server-side cursor.  It is returned only from the
    :meth:`_asyncio.AsyncConnection.stream` and
    :meth:`_asyncio.AsyncSession.stream` methods.

    .. versionadded:: 1.4

    """

    def __init__(self, real_result):
        self._real_result = real_result

        self._metadata = real_result._metadata
        self._unique_filter_state = real_result._unique_filter_state

        # BaseCursorResult pre-generates the "_row_getter".  Use that
        # if available rather than building a second one
        if "_row_getter" in real_result.__dict__:
            self._set_memoized_attribute(
                "_row_getter", real_result.__dict__["_row_getter"]
            )

    def keys(self):
        """Return the :meth:`_engine.Result.keys` collection from the
        underlying :class:`_engine.Result`.

        """
        return self._metadata.keys

    def unique(self, strategy=None):
        """Apply unique filtering to the objects returned by this
        :class:`_asyncio.AsyncResult`.

        Refer to :meth:`_engine.Result.unique` in the synchronous
        SQLAlchemy API for a complete behavioral description.


        """
        self._unique_filter_state = (set(), strategy)
        return self

    def columns(self, *col_expressions):
        # type: (*object) -> AsyncResult
        r"""Establish the columns that should be returned in each row.

        Refer to :meth:`_engine.Result.columns` in the synchronous
        SQLAlchemy API for a complete behavioral description.


        """
        return self._column_slices(col_expressions)

    async def partitions(self, size=None):
        # type: (Optional[Int]) -> Iterator[List[Any]]
        """Iterate through sub-lists of rows of the size given.

        An async iterator is returned::

            async def scroll_results(connection):
                result = await connection.stream(select(users_table))

                async for partition in result.partitions(100):
                    print("list of rows: %s" % partition)

        .. seealso::

            :meth:`_engine.Result.partitions`

        """

        getter = self._manyrow_getter

        while True:
            partition = await greenlet_spawn(getter, self, size)
            if partition:
                yield partition
            else:
                break

    async def fetchone(self):
        # type: () -> Row
        """Fetch one row.

        When all rows are exhausted, returns None.

        This method is provided for backwards compatibility with
        SQLAlchemy 1.x.x.

        To fetch the first row of a result only, use the
        :meth:`_engine.Result.first` method.  To iterate through all
        rows, iterate the :class:`_engine.Result` object directly.

        :return: a :class:`.Row` object if no filters are applied, or None
         if no rows remain.

        """
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            return None
        else:
            return row

    async def fetchmany(self, size=None):
        # type: (Optional[Int]) -> List[Row]
        """Fetch many rows.

        When all rows are exhausted, returns an empty list.

        This method is provided for backwards compatibility with
        SQLAlchemy 1.x.x.

        To fetch rows in groups, use the
        :meth:`._asyncio.AsyncResult.partitions` method.

        :return: a list of :class:`.Row` objects.

        .. seealso::

            :meth:`_asyncio.AsyncResult.partitions`

        """

        return await greenlet_spawn(self._manyrow_getter, self, size)

    async def all(self):
        # type: () -> List[Row]
        """Return all rows in a list.

        Closes the result set after invocation.   Subsequent invocations
        will return an empty list.

        :return: a list of :class:`.Row` objects.

        """

        return await greenlet_spawn(self._allrows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            raise StopAsyncIteration()
        else:
            return row

    async def first(self):
        # type: () -> Row
        """Fetch the first row or None if no row is present.

        Closes the result set and discards remaining rows.

        .. note::  This method returns one **row**, e.g. tuple, by default. To
           return exactly one single scalar value, that is, the first column of
           the first row, use the :meth:`_asyncio.AsyncResult.scalar` method,
           or combine :meth:`_asyncio.AsyncResult.scalars` and
           :meth:`_asyncio.AsyncResult.first`.

        :return: a :class:`.Row` object, or None
         if no rows remain.

        .. seealso::

            :meth:`_asyncio.AsyncResult.scalar`

            :meth:`_asyncio.AsyncResult.one`

        """
        return await greenlet_spawn(self._only_one_row, False, False, False)

    async def one_or_none(self):
        # type: () -> Optional[Row]
        """Return at most one result or raise an exception.

        Returns ``None`` if the result has no rows.
        Raises :class:`.MultipleResultsFound`
        if multiple rows are returned.

        .. versionadded:: 1.4

        :return: The first :class:`.Row` or None if no row is available.

        :raises: :class:`.MultipleResultsFound`

        .. seealso::

            :meth:`_asyncio.AsyncResult.first`

            :meth:`_asyncio.AsyncResult.one`

        """
        return await greenlet_spawn(self._only_one_row, True, False, False)

    async def scalar_one(self):
        # type: () -> Any
        """Return exactly one scalar result or raise an exception.

        This is equivalent to calling :meth:`_asyncio.AsyncResult.scalars` and
        then :meth:`_asyncio.AsyncResult.one`.

        .. seealso::

            :meth:`_asyncio.AsyncResult.one`

            :meth:`_asyncio.AsyncResult.scalars`

        """
        return await greenlet_spawn(self._only_one_row, True, True, True)

    async def scalar_one_or_none(self):
        # type: () -> Optional[Any]
        """Return exactly one or no scalar result.

        This is equivalent to calling :meth:`_asyncio.AsyncResult.scalars` and
        then :meth:`_asyncio.AsyncResult.one_or_none`.

        .. seealso::

            :meth:`_asyncio.AsyncResult.one_or_none`

            :meth:`_asyncio.AsyncResult.scalars`

        """
        return await greenlet_spawn(self._only_one_row, True, False, True)

    async def one(self):
        # type: () -> Row
        """Return exactly one row or raise an exception.

        Raises :class:`.NoResultFound` if the result returns no
        rows, or :class:`.MultipleResultsFound` if multiple rows
        would be returned.

        .. note::  This method returns one **row**, e.g. tuple, by default.
           To return exactly one single scalar value, that is, the first
           column of the first row, use the
           :meth:`_asyncio.AsyncResult.scalar_one` method, or combine
           :meth:`_asyncio.AsyncResult.scalars` and
           :meth:`_asyncio.AsyncResult.one`.

        .. versionadded:: 1.4

        :return: The first :class:`.Row`.

        :raises: :class:`.MultipleResultsFound`, :class:`.NoResultFound`

        .. seealso::

            :meth:`_asyncio.AsyncResult.first`

            :meth:`_asyncio.AsyncResult.one_or_none`

            :meth:`_asyncio.AsyncResult.scalar_one`

        """
        return await greenlet_spawn(self._only_one_row, True, True, False)

    async def scalar(self):
        # type: () -> Optional[Any]
        """Fetch the first column of the first row, and close the result set.

        Returns None if there are no rows to fetch.

        No validation is performed to test if additional rows remain.

        After calling this method, the object is fully closed,
        e.g. the :meth:`_engine.CursorResult.close`
        method will have been called.

        :return: a Python scalar value , or None if no rows remain.

        """
        return await greenlet_spawn(self._only_one_row, False, False, True)

    async def freeze(self):
        """Return a callable object that will produce copies of this
        :class:`_asyncio.AsyncResult` when invoked.

        The callable object returned is an instance of
        :class:`_engine.FrozenResult`.

        This is used for result set caching.  The method must be called
        on the result when it has been unconsumed, and calling the method
        will consume the result fully.   When the :class:`_engine.FrozenResult`
        is retrieved from a cache, it can be called any number of times where
        it will produce a new :class:`_engine.Result` object each time
        against its stored set of rows.

        .. seealso::

            :ref:`do_orm_execute_re_executing` - example usage within the
            ORM to implement a result-set cache.

        """

        return await greenlet_spawn(FrozenResult, self)

    def merge(self, *others):
        """Merge this :class:`_asyncio.AsyncResult` with other compatible result
        objects.

        The object returned is an instance of :class:`_engine.MergedResult`,
        which will be composed of iterators from the given result
        objects.

        The new result will use the metadata from this result object.
        The subsequent result objects must be against an identical
        set of result / cursor metadata, otherwise the behavior is
        undefined.

        """
        return MergedResult(self._metadata, (self,) + others)

    def scalars(self, index=0):
        # type: (Int) -> AsyncScalarResult
        """Return an :class:`_asyncio.AsyncScalarResult` filtering object which
        will return single elements rather than :class:`_row.Row` objects.

        Refer to :meth:`_result.Result.scalars` in the synchronous
        SQLAlchemy API for a complete behavioral description.

        :param index: integer or row key indicating the column to be fetched
         from each row, defaults to ``0`` indicating the first column.

        :return: a new :class:`_asyncio.AsyncScalarResult` filtering object
         referring to this :class:`_asyncio.AsyncResult` object.

        """
        return AsyncScalarResult(self._real_result, index)

    def mappings(self):
        # type() -> AsyncMappingResult
        """Apply a mappings filter to returned rows, returning an instance of
        :class:`_asyncio.AsyncMappingResult`.

        When this filter is applied, fetching rows will return
        :class:`.RowMapping` objects instead of :class:`.Row` objects.

        Refer to :meth:`_result.Result.mappings` in the synchronous
        SQLAlchemy API for a complete behavioral description.

        :return: a new :class:`_asyncio.AsyncMappingResult` filtering object
         referring to the underlying :class:`_result.Result` object.

        """

        return AsyncMappingResult(self._real_result)


class AsyncScalarResult(AsyncCommon):
    """A wrapper for a :class:`_asyncio.AsyncResult` that returns scalar values
    rather than :class:`_row.Row` values.

    The :class:`_asyncio.AsyncScalarResult` object is acquired by calling the
    :meth:`_asyncio.AsyncResult.scalars` method.

    Refer to the :class:`_result.ScalarResult` object in the synchronous
    SQLAlchemy API for a complete behavioral description.

    .. versionadded:: 1.4

    """

    _generate_rows = False

    def __init__(self, real_result, index):
        self._real_result = real_result

        if real_result._source_supports_scalars:
            self._metadata = real_result._metadata
            self._post_creational_filter = None
        else:
            self._metadata = real_result._metadata._reduce([index])
            self._post_creational_filter = operator.itemgetter(0)

        self._unique_filter_state = real_result._unique_filter_state

    def unique(self, strategy=None):
        # type: () -> AsyncScalarResult
        """Apply unique filtering to the objects returned by this
        :class:`_asyncio.AsyncScalarResult`.

        See :meth:`_asyncio.AsyncResult.unique` for usage details.

        """
        self._unique_filter_state = (set(), strategy)
        return self

    async def partitions(self, size=None):
        # type: (Optional[Int]) -> Iterator[List[Any]]
        """Iterate through sub-lists of elements of the size given.

        Equivalent to :meth:`_asyncio.AsyncResult.partitions` except that
        scalar values, rather than :class:`_result.Row` objects,
        are returned.

        """

        getter = self._manyrow_getter

        while True:
            partition = await greenlet_spawn(getter, self, size)
            if partition:
                yield partition
            else:
                break

    async def fetchall(self):
        # type: () -> List[Any]
        """A synonym for the :meth:`_asyncio.AsyncScalarResult.all` method."""

        return await greenlet_spawn(self._allrows)

    async def fetchmany(self, size=None):
        # type: (Optional[Int]) -> List[Any]
        """Fetch many objects.

        Equivalent to :meth:`_asyncio.AsyncResult.fetchmany` except that
        scalar values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._manyrow_getter, self, size)

    async def all(self):
        # type: () -> List[Any]
        """Return all scalar values in a list.

        Equivalent to :meth:`_asyncio.AsyncResult.all` except that
        scalar values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._allrows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            raise StopAsyncIteration()
        else:
            return row

    async def first(self):
        # type: () -> Optional[Any]
        """Fetch the first object or None if no object is present.

        Equivalent to :meth:`_asyncio.AsyncResult.first` except that
        scalar values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._only_one_row, False, False, False)

    async def one_or_none(self):
        # type: () -> Optional[Any]
        """Return at most one object or raise an exception.

        Equivalent to :meth:`_asyncio.AsyncResult.one_or_none` except that
        scalar values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._only_one_row, True, False, False)

    async def one(self):
        # type: () -> Any
        """Return exactly one object or raise an exception.

        Equivalent to :meth:`_asyncio.AsyncResult.one` except that
        scalar values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._only_one_row, True, True, False)


class AsyncMappingResult(AsyncCommon):
    """A wrapper for a :class:`_asyncio.AsyncResult` that returns dictionary values
    rather than :class:`_engine.Row` values.

    The :class:`_asyncio.AsyncMappingResult` object is acquired by calling the
    :meth:`_asyncio.AsyncResult.mappings` method.

    Refer to the :class:`_result.MappingResult` object in the synchronous
    SQLAlchemy API for a complete behavioral description.

    .. versionadded:: 1.4

    """

    _generate_rows = True

    _post_creational_filter = operator.attrgetter("_mapping")

    def __init__(self, result):
        self._real_result = result
        self._unique_filter_state = result._unique_filter_state
        self._metadata = result._metadata
        if result._source_supports_scalars:
            self._metadata = self._metadata._reduce([0])

    def keys(self):
        """Return an iterable view which yields the string keys that would
        be represented by each :class:`.Row`.

        The view also can be tested for key containment using the Python
        ``in`` operator, which will test both for the string keys represented
        in the view, as well as for alternate keys such as column objects.

        .. versionchanged:: 1.4 a key view object is returned rather than a
           plain list.


        """
        return self._metadata.keys

    def unique(self, strategy=None):
        # type: () -> AsyncMappingResult
        """Apply unique filtering to the objects returned by this
        :class:`_asyncio.AsyncMappingResult`.

        See :meth:`_asyncio.AsyncResult.unique` for usage details.

        """
        self._unique_filter_state = (set(), strategy)
        return self

    def columns(self, *col_expressions):
        # type: (*object) -> AsyncMappingResult
        r"""Establish the columns that should be returned in each row."""
        return self._column_slices(col_expressions)

    async def partitions(self, size=None):
        # type: (Optional[Int]) -> Iterator[List[Mapping]]
        """Iterate through sub-lists of elements of the size given.

        Equivalent to :meth:`_asyncio.AsyncResult.partitions` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.

        """

        getter = self._manyrow_getter

        while True:
            partition = await greenlet_spawn(getter, self, size)
            if partition:
                yield partition
            else:
                break

    async def fetchall(self):
        # type: () -> List[Mapping]
        """A synonym for the :meth:`_asyncio.AsyncMappingResult.all` method."""

        return await greenlet_spawn(self._allrows)

    async def fetchone(self):
        # type: () -> Mapping
        """Fetch one object.

        Equivalent to :meth:`_asyncio.AsyncResult.fetchone` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.

        """

        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            return None
        else:
            return row

    async def fetchmany(self, size=None):
        # type: (Optional[Int]) -> List[Mapping]
        """Fetch many objects.

        Equivalent to :meth:`_asyncio.AsyncResult.fetchmany` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.

        """

        return await greenlet_spawn(self._manyrow_getter, self, size)

    async def all(self):
        # type: () -> List[Mapping]
        """Return all scalar values in a list.

        Equivalent to :meth:`_asyncio.AsyncResult.all` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.

        """

        return await greenlet_spawn(self._allrows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await greenlet_spawn(self._onerow_getter, self)
        if row is _NO_ROW:
            raise StopAsyncIteration()
        else:
            return row

    async def first(self):
        # type: () -> Optional[Mapping]
        """Fetch the first object or None if no object is present.

        Equivalent to :meth:`_asyncio.AsyncResult.first` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.


        """
        return await greenlet_spawn(self._only_one_row, False, False, False)

    async def one_or_none(self):
        # type: () -> Optional[Mapping]
        """Return at most one object or raise an exception.

        Equivalent to :meth:`_asyncio.AsyncResult.one_or_none` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._only_one_row, True, False, False)

    async def one(self):
        # type: () -> Mapping
        """Return exactly one object or raise an exception.

        Equivalent to :meth:`_asyncio.AsyncResult.one` except that
        mapping values, rather than :class:`_result.Row` objects,
        are returned.

        """
        return await greenlet_spawn(self._only_one_row, True, True, False)
