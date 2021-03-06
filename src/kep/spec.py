# -*- coding: utf-8 -*-
""":mod:`kep.spec` module contains data structures used as parsing instructions
in :mod:`kep.tables`. Two global variables are used in :mod:`kep.tables`:

   - **UNITS** (dict) is a mapper dictionary to extract units of measurement
     from table headers. It applies to all of CSV file.

   - **SPEC** (:class:`kep.spec.Specification`) contains parsing instructions
     by segment of CSV file:

        - :func:`kep.spec.Specification.get_main_parsing_definition` retrieves
          main (default) parsing definition where most indicators are defined

        - :func:`kep.spec.Specification.get_segment_parsing_definitions` provides
          a list of parsing defintions by segment. We parse CSV file by segment,
          because some table headers repeat themselves in CSV file. Extracting
          a piece out of CSV file gives a very specific input for parsing.

Previously **UNITS** and **SPEC** were initialised based on yaml file, but this
led to many errors, so these data structures are now created internally in
*spec.py*.

*Definition* .get_* methods return the following:

        - *.get_varname_mapper()* - text-to-varname mapper dictionary
        - *.get_required_labels()* - list of (varname, unit) pairs
        - *.get_bounds()* - segment start and end line
        - *.get_reader()* - function name to extract data from unconventional tables


Usage in :mod:`kep.tables`:

.. code-block:: python

    from kep.spec import UNITS, SPEC

    class Tables:
        def __init__(self, _rows, spec=SPEC, units=UNITS):

            self.spec = spec
            self.units = units
            self.required = [make_label(varname, unit) for varname, unit in spec.get_required_labels()]

        def yield_tables(self):
            for csv_segment, pdef in self.make_queue():
                for t in self.extract_tables(csv_segment,
                                             varnames_dict = pdef.get_varname_mapper(),
                                             units_dict = self.units,
                                             funcname = pdef.get_reader(),
                                             required = pdef.get_required_labels()):
                    yield t

        def make_queue(self):
            # has calls:
            for pdef in self.spec.get_segment_parsing_definitions():
                start, end = pdef.get_bounds(self.rowstack.rows)
            pdef = self.spec.get_main_parsing_definition()
"""

from collections import OrderedDict as odict

# mapper dictionary to convert text in table headers to unit of measurement
UNITS = odict([  # 1. MONEY
    ('млрд.долларов', 'bln_usd'),
    ('млрд. долларов', 'bln_usd'),
    ('млрд, долларов', 'bln_usd'),
    ('млрд.рублей', 'bln_rub'),
    ('млрд. рублей', 'bln_rub'),
    ('рублей / rubles', 'rub'),
    ('млн.рублей', 'mln_rub'),
    # 2. RATES OF CHANGE
    ("Индекс физического объема произведенного ВВП, в %", 'yoy'),
    ('в % к декабрю предыдущего года', 'ytd'),
    ('в % к предыдущему месяцу', 'rog'),
    ('в % к предыдущему периоду', 'rog'),
    ('% к концу предыдущего периода', 'rog'),
    # this...
    ('период с начала отчетного года в % к соответствующему периоду предыдущего года', 'ytd'),
    #       ... must precede this
    # because 'в % к предыдущему периоду' is found in
    # 'период с начала отчетного года в % к соответствующему периоду предыдущего года'
    ('в % к соответствующему периоду предыдущего года', 'yoy'),
    ('в % к соответствующему месяцу предыдущего года', 'yoy'),
    ('отчетный месяц в % к предыдущему месяцу', 'rog'),
    ('отчетный месяц в % к соответствующему месяцу предыдущего года', 'yoy'),
    ('период с начала отчетного года', 'ytd'),
    # 3. OTHER UNITS (keep below RATES OF CHANGE)
    ('%', 'pct'),
    ('в % к ВВП', 'gdp_percent'),
    ('млрд. тонно-км', 'bln_tkm'),
    # 4. stub for CPI section
    ("продукты питания", 'rog'),
    ("алкогольные напитки", 'rog'),
    ("непродовольственные товары", 'rog'),
    ("непродовольст- венные товары", 'rog'),
    ("услуги", 'rog')

])

# 'official' names of units used in project front
UNIT_NAMES = {'bln_rub': 'млрд.руб.',
              'bln_usd': 'млрд.долл.',
              'gdp_percent': '% ВВП',
              'mln_rub': 'млн.руб.',
              'rub': 'руб.',
              'rog': '% к пред. периоду',
              'yoy': '% год к году',
              'ytd': 'период с начала года',
              'pct': '%',
              'bln_tkm': 'млрд. тонно-км'}

# validation: all units in mapper dict have an 'offical' name
# this assert is not to be deleted from spec.py
assert set(UNIT_NAMES.keys()) == set(UNITS.values())


def as_list(x: str):
    """Transform string *x* to *[x]*.

       Applied to format user input in ParsingInstruction class.

       Returns:
           list
    """
    if isinstance(x, str):
        return [x]
    elif isinstance(x, list):
        return x
    # tuple is a rare border case, not intended use
    elif isinstance(x, tuple):
        return list(x)
    else:
        msg = "{0} has wrong type <{1}>.".format(
            x, type(x)) + "list or str expected."
        raise TypeError(msg)


# NOTE: these are the assert's you might have wanted to write out before
#       before going to tests
# FIXME: delete this code and note after reading
assert as_list("a") == ["a"]
assert as_list(["a"]) == ["a"]
assert as_list(["a", "b"]) == ["a", "b"]
tup = tuple(["a", "b"])
assert as_list(tup) == ["a", "b"]


class ParsingInstruction:
    """Parsing instructions to extract variable names from table headers.
       Consists of:

       - variable names (eg 'GDP')
       - table header string(s) that correspond to a variable name
         (eg "Oбъем ВВП", "Индекс физического объема произведенного ВВП")
       - required unit(s) of measurement for a variable (eg 'rog', 'rub')
       - (optional) variable description string ("Валовой внутренний продукт")
       - (optional, not implemented) sample data row for each unit

    Attributes:
        varname_mapper (OrderedDict)
        required_labels (list of tuples)
        descriptions (OrderedDict)

    """

    def __init__(self):
        self.varname_mapper = odict()
        self.required_labels = []
        self.descriptions = odict()

    def _verify_inputs(self, varname, required_units):
        # must define variable only once
        if varname in self.varname_mapper.values():
            msg = "Variable name <{}> already defined".format(varname)
            raise ValueError(msg)
        # *units* must be UNITS.values()
        for ru in as_list(required_units):
            if ru not in UNITS.values():
                msg = "Unit <{}> not defined".format(ru)
                raise ValueError(msg)

    def append(self, varname, text, required_units, desc=False):
        """Add a parsing instructions for an individual variable.

            Args:
              varname (str):
              text (str or list):
              required_units (str or list):
              desc (str): (optional)
        """

        # validate arguments
        self._verify_inputs(varname, required_units)

        # convert from user interface
        header_strings = as_list(text)
        if desc is False:
            desc = header_strings[0]
        required_units = as_list(required_units)

        # make internal variables
        _vmapper = odict([(hs, varname) for hs in header_strings])
        _required_labels = list((varname, unit) for unit in required_units)
        _desc = {varname: desc}

        # update internal variables (by dict update and list extend)
        self.varname_mapper.update(_vmapper)
        self.required_labels.extend(_required_labels)
        self.descriptions.update(_desc)

    # RFE(EP): keep __eq__() only if it used in testing, delete this method
    # otherwise
    def __eq__(self, x):
        # FIXME: after reading delete this code and comment
        # ERROR: in testing x may be a mock object of
        #        different type, just a class, restricting it to ParsingInstruction is wrong
        # assert(isinstance(x, ParsingInstruction))

        # WARNING: different order of required_labels will make objects not
        # equal
        flag1 = self.required_labels == x.required_labels
        flag2 = self.varname_mapper == x.varname_mapper
        return bool(flag1 and flag2)

# EP: not edited below this line
# -----------------------------------------------------------------------------


class Definition(object):

    def __init__(self, scope=False, reader=False):
        self.instr = ParsingInstruction()
        if scope:
            self.set_scope(scope)
        else:
            self.scope = False
        if reader:
            self.set_reader(reader)
        else:
            self.reader = False

    def append(self, *arg, **kwarg):
        self.instr.append(*arg, **kwarg)

    def set_scope(self, sc):
        if isinstance(sc, Scope):
            self.scope = sc
        else:
            raise TypeError(sc)

    def set_reader(self, funcname: str):
        from kep.splitter import FUNC_MAPPER
        if isinstance(funcname, str) and funcname in FUNC_MAPPER.keys():
            self.reader = funcname
        else:
            raise ValueError(funcname)

    def get_varnames(self):
        varnames = self.get_varname_mapper().values()
        return list(set(varnames))

    # WONTFIX: direct access to internals

    def get_varname_mapper(self):
        return self.instr.varname_mapper

    def get_required_labels(self):
        return self.instr.required_labels

    def get_reader(self):
        return self.reader

    def get_bounds(self, rows):
        return self.scope.get_bounds(rows)


class Scope():
    """Start and end lines for CSV file segment and associated variables
       defintion.

       Holds several versions of start and end line, return applicable line
       for a particular CSV file versions. This solves problem of different
       headers for same table at various releases.
    """

    def __init__(self, start, end):  # , reader=None):
        self.__markers = []
        self.add_bounds(start, end)
    #     self.definition = Definition(reader)

    def add_bounds(self, start, end):
        if start and end:
            self.__markers.append(dict(start=start, end=end))
        else:
            raise ValueError("Cannot accept empty line as Scope() boundary")

    def get_bounds(self, rows):
        """Get start and end line markers, which can be found in *rows*"""
        # rows = list(rows) #faster
        rows = [r for r in rows]  # consume iterator
        for marker in self.__markers:
            s = marker['start']
            e = marker['end']
            if self._is_found(s, rows) and self._is_found(e, rows):
                return s, e
        msg = self._error_message(rows)
        raise ValueError(msg)

    @staticmethod
    def _is_found(line, rows):
        """Return True, is *line* found at start of any entry in *rows*"""
        for r in rows:
            if r.startswith(line):
                return True
        return False

    def _error_message(self, rows):
        msg = []
        msg.append("start or end line not found in *rows*")
        for marker in self.__markers:
            s = marker['start']
            e = marker['end']
            msg.append("is_found: {} <{}>".format(self._is_found(s, rows), s))
            msg.append("is_found: {} <{}>".format(self._is_found(e, rows), e))
        return "\n".join(msg)

    def __repr__(self):  # possible misuse of special method consider using __str__
        s = self.__markers[0]['start'][:10]
        e = self.__markers[0]['end'][:10]
        return "bound by start <{}...> and end <{}...>".format(s, e)


class Specification:
    """EDIT: Specification holds a list of defintions in two variables:

       .main ()
       .scope (segment defintitions)

    """

    def __init__(self, default):
        # main parsing definition
        self.main = default
        # additional parsing instructions for segments
        self.segment_definitions = []

    def append(self, pdef):
        self.segment_definitions.append(pdef)
        # WONTFIX: validate order of markers - ends are not starts

    def get_main_parsing_definition(self):
        return self.main

    def get_segment_parsing_definitions(self):
        return self.segment_definitions

    def all_definitions(self):
        return [self.main] + self.segment_definitions

    def get_required_labels(self):
        req = []
        for pdef in self.all_definitions():
            req.extend(pdef.get_required_labels())
        return req

    def get_varnames(self):
        varnames = set()
        for pdef in self.all_definitions():
            varnames.add(pdef.get_varnames())
        return list(varnames)


# creating definitions
# step 1 - global (default) parsing defintion
main = Definition()
main.append(varname="GDP",
            text=["Oбъем ВВП",
                  "Индекс физического объема произведенного ВВП, в %",
                  "Валовой внутренний продукт"],
            required_units=["bln_rub", "yoy"],
            desc="Валовый внутренний продукт (ВВП)")
# sample="1999	4823	901	1102	1373	1447"
main.append(varname="INDPRO",
            text="Индекс промышленного производства",
            required_units=["yoy", "rog"],
            desc="Промышленное производство")
main.append(varname="UNEMPL",
            text=["Уровень безработицы"],
            required_units=["pct"])
main.append(
    "WAGE_NOMINAL",
    "Среднемесячная номинальная начисленная заработная плата работников организаций",
    "rub")
main.append("WAGE_REAL",
            "Реальная начисленная заработная плата работников организаций",
            ["yoy", "rog"])
main.append("TRANSPORT_FREIGHT",
            "Коммерческий грузооборот транспорта",
            "bln_tkm")

# step 2 - create Specification based on 'main'
SPEC = Specification(default=main)


# step 3 - segment definitions
# -- investment
sc = Scope("1.6. Инвестиции в основной капитал",
           "1.6.1. Инвестиции в основной капитал организаций")
sc.add_bounds("1.7. Инвестиции в основной капитал",
              "1.7.1. Инвестиции в основной капитал организаций")
d = Definition(scope=sc)
d.append("INVESTMENT",
         "Инвестиции в основной капитал",
         ["bln_rub", "yoy", "rog"])
SPEC.append(d)


# -- EXIM
sc = Scope("1.9. Внешнеторговый оборот – всего",
           "1.9.1. Внешнеторговый оборот со странами дальнего зарубежья")
sc.add_bounds("1.10. Внешнеторговый оборот – всего",
              "1.10.1. Внешнеторговый оборот со странами дальнего зарубежья")
sc.add_bounds("1.10. Внешнеторговый оборот – всего",
              "1.10.1.Внешнеторговый оборот со странами дальнего зарубежья")
d = Definition(scope=sc)
d.append("EXPORT_GOODS",
         ["экспорт товаров – всего",
          "Экспорт товаров"],
         "bln_usd")
d.append("IMPORT_GOODS",
         ["импорт товаров – всего",
          "Импорт товаров"],
         "bln_usd")
SPEC.append(d)

# -- PPI
# add here

# -- CPI
sc = Scope(start="3.5. Индекс потребительских цен",
           end="4. Социальная сфера")
d = Definition(scope=sc)
d.append("CPI",
         text="Индекс потребительских цен",
         required_units="rog",
         desc="Индекс потребительских цен (ИПЦ)")
d.append("CPI_NONFOOD",
         text=["непродовольственные товары",
               "непродовольст- венные товары"],
         required_units="rog",
         desc="ИПЦ (непродтовары)")
d.append("CPI_FOOD",
         "продукты питания",
         ['rog'],
         "ИПЦ (продтовары)")
d.append("CPI_SERVICES",
         "услуги",
         ['rog'],
         "ИПЦ (услуги)")
d.append("CPI_ALCOHOL",
         "алкогольные напитки",
         ['rog'],
         "ИПЦ (алкоголь)")
SPEC.append(d)


sc = Scope("1.12. Оборот розничной торговли",
           "1.12.1. Оборот общественного питания")
sc.add_bounds("1.13. Оборот розничной торговли",
              "1.13.1. Оборот общественного питания")
d = Definition(scope=sc)
d.append("RETAIL_SALES",
         "Оборот розничной торговли",
         ["bln_rub", "yoy", "rog"])
d.append("RETAIL_SALES_FOOD",
         ["продовольственные товары",
          "пищевые продукты, включая напитки и табачные изделия",
          "пищевые продукты, включая напитки, и табачные изделия"],
         ["bln_rub", "yoy", "rog"])
d.append("RETAIL_SALES_NONFOOD",
         "непродовольственные товары",
         ["bln_rub", "yoy", "rog"])
SPEC.append(d)

sc = Scope("2.1.1. Доходы (по данным Федерального казначейства)",
           "2.1.2. Расходы (по данным Федерального казначейства)")
d = Definition(scope=sc, reader="fiscal")
d.append("GOV_REVENUE_ACCUM_CONSOLIDATED",
         "Консолидированный бюджет",
         "bln_rub")
d.append("GOV_REVENUE_ACCUM_FEDERAL",
         "Федеральный бюджет",
         "bln_rub")
d.append("GOV_REVENUE_ACCUM_SUBFEDERAL",
         "Консолидированные бюджеты субъектов Российской Федерации",
         "bln_rub")
SPEC.append(d)


sc = Scope("2.1.2. Расходы (по данным Федерального казначейства)",
           "2.1.3. Превышение доходов над расходами")
d = Definition(scope=sc, reader="fiscal")
d.append("GOV_EXPENSE_ACCUM_CONSOLIDATED",
         "Консолидированный бюджет",
         "bln_rub")
d.append("GOV_EXPENSE_ACCUM_FEDERAL",
         "Федеральный бюджет",
         "bln_rub")
d.append("GOV_EXPENSE_ACCUM_SUBFEDERAL",
         "Консолидированные бюджеты субъектов Российской Федерации",
         "bln_rub")
SPEC.append(d)


sc = Scope("2.1.3. Превышение доходов над расходами",
           "2.2. Сальдированный финансовый результат")
d = Definition(scope=sc, reader="fiscal")
d.append("GOV_SURPLUS_ACCUM_FEDERAL",
         "Федеральный бюджет",
         "bln_rub")
d.append("GOV_SURPLUS_ACCUM_SUBFEDERAL",
         "Консолидированные бюджеты субъектов Российской Федерации",
         "bln_rub")
SPEC.append(d)


# *** PRIORITY_HIGHER:

# FIXME: bring usage examples from issue #38 to documentation - module docstrings
# FIXME: write docstrings
# FIXME: asserts/tests

# ** PRIORITY_LOWER:

# TODO: add more definitons
# TODO: transformations layer diff GOV_ACCUM
# PROPOSAL/DISCUSS: use sample in required
