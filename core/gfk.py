"""
GenericForeignKey helpers (OP-3343).

prefetch_gfk() loads the GenericForeignKey targets of a whole page at once, instead
of one query per row when a resolver reads `row.<gfk>`. Its targets are shared
between the rows pointing at the same object: a resolver must not change them
(for example pop '_state' from their __dict__) but serialise a copy.
"""
from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db.models import prefetch_related_objects
from graphene.utils.str_converters import to_camel_case
from graphql.language import FragmentSpreadNode


def requested_fields(info):
    """Names of every field selected under the resolved field, fragments included."""
    names = set()

    def walk(selection_set):
        for selection in selection_set.selections if selection_set else ():
            if isinstance(selection, FragmentSpreadNode):
                walk(info.fragments[selection.name.value].selection_set)
                continue
            if getattr(selection, "name", None):
                names.add(selection.name.value)
            walk(selection.selection_set)

    for field_node in info.field_nodes:
        walk(field_node.selection_set)
    return names


def _generic_foreign_key(model, name):
    # A history model (simple_history) has the GenericForeignKey's columns, not the field.
    for candidate in (model, getattr(model, "instance_type", None)):
        field = getattr(candidate, name, None) if candidate else None
        if isinstance(field, GenericForeignKey):
            return field, candidate is model
    raise ValueError(f"{model.__name__} has no GenericForeignKey named {name!r}")


def _target_querysets(related):
    querysets = []
    for label, relations in (related or {}).items():
        try:
            model = apps.get_model(label)
        except LookupError:
            continue  # module not installed
        # _base_manager, as the GenericForeignKey itself uses: no target is hidden.
        querysets.append(model._base_manager.select_related(*relations))
    return querysets


def prefetch_gfk(queryset, *names, info=None, reads=None, related=None):
    """
    Load the GenericForeignKeys `names` of the queryset's rows, and their content
    types, in a few queries per page rather than one per row.

    info: the GraphQL resolve info. With it, a GenericForeignKey is only loaded when
        the query selects a field that reads its target, and its content type when
        the query selects that or the type itself (`subjectType`, `subjectTypeName`).
    reads: {name: GraphQL field names reading the target}. By default, the
        GenericForeignKey's own camelCase name (`subject`).
    related: {"app_label.Model": relations} loaded with every target of that model,
        e.g. {"insuree.Family": ("head_insuree",)}. Models of modules that are not
        installed are skipped.
    """
    requested = requested_fields(info) if info is not None else None
    reads = reads or {}
    after_fetch = []
    for name in names:
        field, on_model = _generic_foreign_key(queryset.model, name)
        target_fields = set(reads.get(name, (to_camel_case(name),)))
        type_fields = {to_camel_case(field.ct_field), to_camel_case(f"{field.ct_field}_name")}
        load_target = requested is None or bool(requested & target_fields)
        load_type = load_target or requested is None or bool(requested & type_fields)
        lookup = GenericPrefetch(name, _target_querysets(related))
        if on_model:
            if load_target:
                queryset = queryset.prefetch_related(lookup)
            if load_type:
                queryset = queryset.select_related(field.ct_field)
        else:
            # Building the instance drops what select_related loaded: prefetch the type too.
            after_fetch += ([field.ct_field] if load_type else []) + ([lookup] if load_target else [])
    return _prefetch_after_fetch(queryset, after_fetch) if after_fetch else queryset


_after_fetch_classes = {}


def _prefetch_after_fetch(queryset, lookups):
    """
    For history querysets returning instances (`Model.history...as_instances()`):
    the rows only become instances once fetched, so the lookups run then, for the page.
    """
    base = type(queryset)
    cls = _after_fetch_classes.get(base)
    if cls is None:
        class PrefetchAfterFetch(base):
            def _clone(self):
                clone = super()._clone()
                clone._after_fetch_lookups = self._after_fetch_lookups
                return clone

            def _fetch_all(self):
                fetched = self._result_cache is not None
                super()._fetch_all()
                if not fetched and self._result_cache:
                    instances = [obj for obj in self._result_cache if not isinstance(obj, self.model)]
                    if instances:
                        prefetch_related_objects(instances, *self._after_fetch_lookups)

        cls = _after_fetch_classes[base] = PrefetchAfterFetch
    queryset = queryset._clone()
    previous = getattr(queryset, "_after_fetch_lookups", ())
    queryset.__class__ = cls
    queryset._after_fetch_lookups = (*previous, *lookups)
    return queryset
