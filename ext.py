#!/usr/bin/env python
"""Functions that constitute the :obj:`argdoc` extension for `Sphinx`_.

User functions
--------------
:func:`noargdoc`
    Function decorator that forces :obj:`argdoc` to skip a :term:`main-like function`
    it would normally process
    
Developer functions
-------------------
:func:`process_subprogram_container`
    Extract tables from all subprogram
    :class:`ArgumentParsers <argparse.ArgumentParser>`
    contained by an enclosing :class:`~argparse.ArgumentParser`

:func:`process_single_or_subprogram`
    Extract tables of arguments from an :class:`~argparse.ArgumentParser`
    that has no subprograms

:func:`process_argparser`
    Delegate a given :class:`~argparse.ArgumentParser` to 
    :func:`process_subprogram_container` or :func:`process_single_or_subprogram`

:func:`add_args_to_module_docstring`
    Event handler called by `Sphinx`_ upon `autodoc-process-docstring` events

:func:`setup`
    Register the extension with the running `Sphinx`_ instance
"""
import re
import shlex
import subprocess
import sphinx
import argdoc

#===============================================================================
# INDEX: various constants
#===============================================================================

_OTHER_HEADER_LINES = """Script contents
---------------""".split("\n")

_SUBCOMMAND_HEADER = "%sSubcommand arguments\n%s--------------------\n"

_REQUIRED = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
]
"""Other `Sphinx`_ extensions required by :py:obj:`argdoc`"""

patterns = { "section_title"      : r"^(\w+.*):$",
             "opt_only"           : r"^  (-?[^\s]+(, --[^\s]+)?)$",
             "opt_plus_args"      : r"^  (-+[^\s]+)((?: [^-\s]+)+)(?:(?:, (--[^\s]+))((?: [^\s]+)+))?$",
             "opt_plus_desc"      : r"^  (?P<left>-?[^\s]+(,\s--[^\s]+)?)\s\s+(?P<right>.*)",
             "opt_plus_args_desc" : r"^  (?P<left>(-?-[^\s]+)( [^-\s]+)+( --[^\s]+( [^\s]+)+)?)  +(?P<right>\w+.*)$",
             "continue_desc"      : r"^ {24}(.*)",
             "section_desc"       : r"^ (\s[^- ]+)+$",
             "subcommands"        : r"^subcommands:$",
             "subcommand_names"   : r"^  {((?:\w+)(?:(?:,(?:\w+))+)?)}$"             
            }
"""Regular expressions describing components of docstrings created by :py:mod:`argparse`"""

patterns = { K : re.compile(V) for K,V in patterns.items() }  

#===============================================================================
# INDEX: function decorators
#===============================================================================

def noargdoc(func):
    """Decorator that forces argdoc to skip processing of `func` 
    
    Parameters
    ----------
    func : function
        :term:`main-like function` of a script

    
    Returns
    -------
    func
        wrapped function
    """
    func.__dict__["noargdoc"] = True
    return func

#===============================================================================
# INDEX: docstring-processing functions
#===============================================================================

def process_subprogram_container(app,obj,help_lines,start_line,indent_size=4,section_head=False):
    """Processes help output from an :py:class:`argparse.ArgumentParser`
    from a program that includes one or more subprograms.  Called by
    :func:`process_argparser`
    
    Parameters
    ----------
    app
        Sphinx application
            
    obj : module
        Module containing :term:`main-like function`
            
    help_lines : list
        List of strings, each corresponding to a line of output from having
        passed ``--help`` as an argument to the :term:`main-like function`

    start_line : int
        Line where token `'subcommands: '` was found in argparser output
    
    indent_size : int, optional
        Number of spaces to prepend before output. This is significant,
        because whitespace is significant in reStructuredText, and 
        incorrect indentation size will muddle the rendering. (Default: `4`)
    
    section_head : bool, optional
        If `True`, a section header for "Command-line arguments" will be included.
        This messes up parsing for function docstrings, but is fine for module
        docstrings (Default: `False`).
    
    Returns
    -------
    list
        List of strings encoding reStructuredText table of command-line
        arguments for all subprograms in the containing argparser
    """
    out_lines = (_SUBCOMMAND_HEADER % (" "*indent_size," "*indent_size)).split("\n")
    for line in help_lines[start_line+1:]:
        match = patterns["subcommand_names"].search(line.strip("\n")) 
        if match is not None:
            subcommands = match.groups()[0].split(",")
            break
    
    app.debug("%s subcommands: %s" % (obj.__name__,", ".join(subcommands)))
    for subcommand in subcommands:
        call = shlex.split("python -m %s %s --help" % (obj.__name__,subcommand))
        try:
            proc = subprocess.Popen(call,stdout=subprocess.PIPE)
            sub_help_lines = proc.communicate()[0].split("\n")
            out_lines.extend(process_single_or_subprogram(sub_help_lines,
                                                          indent_size=indent_size,
                                                          section_head=section_head,
                                                          section_name="``%s`` subprogram" % subcommand))            
        except subprocess.CalledProcessError as e:
            out  = ("-"*75) + "\n" + e.output + "\n" + ("-"*75)
            out += "Could not call module %s as '%s'. Output:\n"% (obj.__name__, e.cmd)
            out += e.output
            out += ("-"*75) + "\n"
            app.warn(out)

    return out_lines

def process_single_or_subprogram(help_lines,indent_size=4,section_head=False,section_name="Command-line arguments"):
    """Processes help output from an :py:class:`argparse.ArgumentParser`
    of subprograms, or of a program that has no subprograms. Called by
    :func:`process_argparser`
    
    Parameters
    ----------
    help_lines : list
        List of strings, each corresponding to a line of output from having
        passed ``--help`` as an argument to the :term:`main-like function`
    
    indent_size : int, optional
        Number of spaces to prepend before output. This is significant,
        because whitespace is significant in reStructuredText, and 
        incorrect indentation size will muddle the rendering. (Default: `4`)
    
    section_head : bool, optional
        If `True`, a section header for "Command-line arguments" will be included.
        This messes up parsing for function docstrings, but is fine for module
        docstrings (Default: `False`).
    
    Returns
    -------
    list
        List of strings encoding reStructuredText table of arguments
        for program or subprogram
    """
    started = False

    out_lines = []
    col1      = []
    col2      = []
    section_title = []
    section_desc  = []
    
    for line in help_lines:
        line = line.rstrip()
        if len(line.strip()) == 0 and started == True:
            # close table and write out previous section
            if len(col1) > 0 and len(col2) > 0:
                col1_width = 1 + max([len(X) for X in col1]) + 4
                col2_width = max([len(X) for X in col2])
                out_lines.append("")
                out_lines.append("")
                out_lines.extend(section_title)
                out_lines.extend(section_desc)
                out_lines.append("")
                out_lines.append( (" "*indent_size)+("="*col1_width) + " " + ("="*col2_width))# + "\n" )
                out_lines.append( (" "*indent_size)+"*Option*" + " "*(1 + col1_width - 8) + "*Description*")# + "\n" )
                out_lines.append( (" "*indent_size)+("="*col1_width) + " " + ("="*col2_width))# + "\n" )
                 
                for c1, c2 in zip(col1,col2):
                    out_lines.append((" "*indent_size)+ "``" + c1 + "``" + (" "*(1+col1_width-len(c1))) + c2)# + "\n" )
     
                out_lines.append( (" "*indent_size)+("="*col1_width) + " " + ("="*col2_width))#  + "\n"  )
                out_lines.append("")
                
                section_title = []
                section_desc  = []
                col1 = []
                col2 = []
            
        #elif patterns["section_title"].search(line):
        #FIXME: this is a kludge to deal with __doc__ lines that have trailing colons
        #       and will not work if the first argument section is not one of the following
        #       "positional arguments:" or "optional arguments:"
        elif line.startswith("positional arguments:") or line.startswith("optional arguments:"):
            
            if started == False:
                started = True
                if section_head == True:
                    stmp1 = "%s%s" % (" "*indent_size,section_name)
                    stmp2 = "%s%s" % (" "*indent_size,"-"*len(section_name))
                    out_lines.append(stmp1)
                    out_lines.append(stmp2)
            
            # start section
            match = patterns["section_title"].search(line)
            
            section_title = ["%s%s" % (" "*indent_size,match.groups()[0].capitalize()),
                             "%s%s" % (" "*indent_size,("."*len(match.groups()[0]))),
                            ]
        elif patterns["section_title"].search(line) is not None and not line.startswith("usage:"):
            match = patterns["section_title"].search(line)
            
            section_title = ["%s%s" % (" "*indent_size,match.groups()[0].capitalize()),
                             "%s%s" % (" "*indent_size,("\""*len(match.groups()[0]))),
                            ]
        elif patterns["section_desc"].search(line) is not None and started == True:
            section_desc.append(line.strip())
            
        elif patterns["opt_only"].search(line) is not None and started == True:
            col1.append(line.strip())
            col2.append("")
        elif patterns["opt_plus_args"].search(line) is not None and started == True:
            col1.append(line.strip())
            col2.append("")
        elif patterns["continue_desc"].search(line) is not None and started == True:
            col2[-1] += line.strip("\n")
        elif patterns["opt_plus_desc"].search(line) is not None and started == True:
            match = patterns["opt_plus_desc"].search(line).groupdict()
            col1.append(match["left"])
            col2.append(match["right"])
        elif patterns["opt_plus_args_desc"].search(line) is not None and started == True:
            match = patterns["opt_plus_args_desc"].search(line).groupdict()
            col1.append(match["left"])
            col2.append(match["right"])
    
    return out_lines

def process_argparser(app,obj,help_lines,indent_size=4,section_head=False):
    """Processes help output from an :py:class:`argparse.ArgumentParser`
    into a set of reStructuredText tables, probing subcommand parsers as needed.
    
    Parameters
    ----------
    app
        Sphinx application
    
    obj : module
        Module containing :term:`main-like function`
    
    help_lines : list
        List of strings, each corresponding to a line of output from having
        passed ``--help`` as an argument to the :term:`main-like function`
    
    indent_size : int, optional
        Number of spaces to prepend before output. This is significant,
        because whitespace is significant in reStructuredText, and 
        incorrect indentation size will muddle the rendering. (Default: `4`)
    
    section_head : bool, optional
        If `True`, a section header for "Command-line arguments" will be included.
        This messes up parsing for function docstrings, but is fine for module
        docstrings (Default: `False`).
    
    Returns
    -------
    list
        List of strings corresponding to reStructuredText tables
    """
    has_subcommands = False
    for n,line in enumerate(help_lines):
        if patterns["subcommands"].match(line.strip("\n")) is not None:
            has_subcommands = True
            break
    if has_subcommands == True:
        app.debug("%s has subcommands" % obj.__name__)        
        out_lines = process_subprogram_container(app,obj,help_lines,n,
                                                 indent_size=indent_size,
                                                 section_head=section_head)

    else:
        app.debug("%s has no subcommands" % obj.__name__)
        out_lines = process_single_or_subprogram(help_lines,
                                                 indent_size=indent_size,
                                                 section_head=section_head)                                  

    return out_lines

def add_args_to_module_docstring(app,what,name,obj,options,lines):
    """Insert a table listing and describing an executable script's command-line
    arguments into its ``:automodule:`` documentation.
    
    Any :term:`main-like function` decorated with the :func:`noargdoc` decorator
    will be skipped. A function is determined to be a :term:`main-like function`
    if its name matches the name set in the configuration option
    ``argdoc_main_func`` inside ``conf.py``. The default value for
    ``argdoc_main_func`` is `main`.
    
    Notes
    -----
    Per the `Sphinx`_ spec, this function modifies `lines` in place.
    
    This will only work for :term:`executable scripts` that use
    :mod:`argparse`.
    
    
    Parameters
    ----------
    app
        Sphinx application instance
    
    what : str
        Type of object (e.g. "module", "function", "class")
    
    name : str
        Fully-qualified name of object
    
    obj : object
        Object to skip or not
    
    options : object
        Options given to the directive, whose boolean properties are set to `True`
        if their corresponding flag was given in the directive

    lines : list
        List of strings encoding the module docstrings after `Sphinx`_ processing

    Raises
    ------
    ConfigError
       If `argdoc_main_func` is defined in ``conf.py`` and is not a `str`
    """
    funcname = app.config.argdoc_main_func
    if not isinstance(funcname,str):
        message = "Incorrect type for `argdoc_main_func. Expected `str`, found, `%s` with value `%s`)" % (type(funcname),funcname)
        raise ConfigError(message)

    if what == "module" and obj.__dict__.get(funcname,None) is not None:
        if obj.__dict__.get(funcname).__dict__.get("noargdoc",False) == False:
            call = shlex.split("python -m %s --help" % obj.__name__)
            try:
                proc = subprocess.Popen(call,stdout=subprocess.PIPE)
                help_lines = proc.communicate()[0].split("\n")
            except subprocess.CalledProcessError as e:
                out  = ("-"*75) + "\n" + e.output + "\n" + ("-"*75)
                out += "Could not call module %s as '%s'. Output:\n"% (obj.__name__, e.cmd)
                out += e.output
                out += ("-"*75) + "\n"
                app.warn(out)
            try:
                out_lines = process_argparser(app,obj,help_lines,indent_size=0,section_head=True)
                lines.extend(out_lines)
                lines.extend(_OTHER_HEADER_LINES)
            except IndexError as e:
                app.warn("Error processing argparser into docstring for module %s: " % obj.__name__)

#===============================================================================
# INDEX: extension setup
#===============================================================================

def setup(app):
    """Set up :obj:`argdoc` extension and register with `Sphinx`_
    
    Parameters
    ----------
    app
        Sphinx application instance
    """

    metadata = { "version" : argdoc.__version__
               }

    for ext in _REQUIRED:
        app.setup_extension(ext)
    
    app.connect("autodoc-process-docstring",add_args_to_module_docstring)
    app.add_config_value("argdoc_main_func","main","env")

    if sphinx.version_info >= (1,3,0,'',0):
        return metadata
