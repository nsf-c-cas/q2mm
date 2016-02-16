"""
Extracts QM data from reference files or calculates FF data.

Takes a sequence of keywords corresponding to various
datatypes (ex. mb = MacroModel bond lengths) followed by filenames,
and extracts that particular data type from the file. Note that the
order of filenames is important.
"""
import argparse
import itertools
import logging
import logging.config
import numpy as np
import os
import sys
import textwrap

import constants as co
import compare
import datatypes
import filetypes

logger = logging.getLogger(__name__)

# Commands where we need to load the force field.
COM_LOAD_FF    = ['ma', 'mb', 'mt', 'ja', 'jb', 'jt']
# Commands related to Gaussian.
COM_GAUSSIAN   = ['ge', 'geo', 'geigz', 'geigz2']
# Commands related to Jaguar (Schrodinger).
COM_JAGUAR     = ['je', 'jeo', 'jeigz', 'jq', 'jqh']
# Commands related to MacroModel (Schrodinger).
COM_MACROMODEL = ['ja', 'jb', 'jt', 'ma', 'mb', 'mcs', 'mcs2',
                  'mcs3', 'me', 'meo', 'mjeig', 'mgeig',
                  'mq', 'mqh', 'mt']
# All other commands.
COM_OTHER = ['r']
# All possible commands.
COM_ALL = COM_GAUSSIAN + COM_JAGUAR + COM_MACROMODEL + COM_OTHER

def main(args):
    """
    Arguments
    ---------
    args : string
           Evaluated using parser returned by return_calculate_parser().
    """
    parser = return_calculate_parser()
    opts = parser.parse_args(args)
    # commands looks like:
    # {'me': [['a1.01.mae', 'a2.01.mae', 'a3.01.mae'], 
    #         ['b1.01.mae', 'b2.01.mae']],
    #  'mb': [['a1.01.mae'], ['b1.01.mae']],
    #  'jeig': [['a1.01.in,a1.out', 'b1.01.in,b1.out']]
    # }
    commands = {key: value for key, value in opts.__dict__.iteritems() if key
                in COM_ALL and value}
    pretty_all_commands(commands)
    # commands_for_filenames looks like:
    # {'a1.01.mae': ['me', 'mb'],
    #  'a1.01.in': ['jeig'],
    #  'a1.out': ['jeig'],
    #  'a2.01.mae': ['me'],
    #  'a3.01.mae': ['me'],
    #  'b1.01.mae': ['me', 'mb'],
    #  'b1.01.in': ['jeig'],
    #  'b1.out': ['jeig'],
    #  'b2.01.mae': ['me']
    # }
    commands_for_filenames = sort_commands_by_filename(commands)
    pretty_commands_for_files(commands_for_filenames)
    # inps looks like:
    # {'a1.01.mae': <__main__.Mae object at 0x1110e10>,
    #  'a1.01.in': None,
    #  'a1.out': None,
    #  'a2.01.mae': <__main__.Mae object at 0x1733b23>,
    #  'a3.01.mae': <__main__.Mae object at 0x1853e12>,
    #  'b1.01.mae': <__main__.Mae object at 0x2540e10>,
    #  'b1.01.in': None,
    #  'b1.out': None,
    #  'b2.01.mae': <__main__.Mae object at 0x1353e11>,
    # }
    inps = {}
    for filename, commands_for_filename in commands_for_filenames.iteritems():
        if any(x in COM_MACROMODEL for x in commands_for_filename):
            if os.path.splitext(filename)[1] == '.mae':
                inps[filename] = filetypes.Mae(
                    os.path.join(opts.directory, filename))
                inps[filename].commands = commands_for_filename
                inps[filename].write_com()
        else:
            inps[filename] = None
    if opts.norun:
        logger.log(15, "  -- Skipping MacroModel calculations.")
    else:
        for filename, some_class in inps.iteritems():
            # Works if some class is None too.
            if hasattr(some_class, 'run'):
                some_class.run(check_tokens=opts.check)
    data = collect_data(commands, inps, direc=opts.directory)
    if opts.weight:
        compare.import_weights(data)
    if opts.doprint:
        pretty_data(data, log_level=None)
    return data

def return_calculate_parser(add_help=True, parents=None):
    '''
    Command line argument parser for calculate.

    Arguments
    ---------
    add_help : bool
               Whether or not to add help to the parser. Default
               is True.
    parents : argparse.ArgumentParser
              Parent parser incorporated into this parser. Default
              is None.
    '''
    # Whether or not to add help. You may not want to add help if
    # these arguments are being used in another, higher level parser.
    if parents is None: parents = []
    if add_help:
        parser = argparse.ArgumentParser(
            description=__doc__, parents=parents)
    else:
        parser = argparse.ArgumentParser(
            add_help=False, parents=parents)
    # GENERAL OPTIONS
    opts = parser.add_argument_group("calculate options")
    opts.add_argument(
        '--directory', '-d', type=str, metavar='somepath', default=os.getcwd(),
        help=('Directory searched for files '
              '(ex. *.mae, *.log, mm3.fld, etc.). '
              'Subshell commands (ex. MacroModel) are executed from here. '
              'Default is the current directory.'))
    opts.add_argument(
        '--doprint', '-p', action='store_true',
        help=("Logs data. Can generate extensive log files."))
    opts.add_argument(
        '--ffpath', '-f', type=str, metavar='somepath',
        help=("Path to force field. Only necessary for certain data types "
              "if you don't provide the substructure name."))
    opts.add_argument(
        '--nocheck', '-nc', action='store_false', dest='check', default=True,
        help=("By default, Q2MM checks whether MacroModel tokens are "
              "available before attempting a MacroModel calculation. If this "
              "option is supplied, MacroModel will not check for tokens "
              "first."))
    opts.add_argument(
        '--norun', '-n', action='store_true',
        help="Don't run 3rd party software.")
    opts.add_argument(
        '--subnames',  '-s', type=str, nargs='+',
        metavar='"Substructure Name OPT"',
        help=("Names of the substructures containing parameters to "
              "optimize in a mm3.fld file."))
    opts.add_argument(
        '--weight', '-w', action='store_true',
        help='Add weights to data points.')
    # DATA TYPES
    data_args = parser.add_argument_group("calculate data types")
    data_args.add_argument(
        '-ge', type=str, nargs='+', action='append',
        default=[], metavar='somename.log',
        help=('Gaussian energies.'))
    data_args.add_argument(
        '-geo', type=str, nargs='+', action='append',
        default=[], metavar='somename.log',
        help=('Gaussian energies. Same as -ge, except the files selected '
              'by this command will have their energies compared to those '
              'selected by -meo.'))
    data_args.add_argument(
        '-geigz', type=str, nargs='+', action='append',
        default=[], metavar='somename.log',
        help=('Gaussian eigenmatrix. Incluldes all elements, but zeroes '
              'all off-diagonal elements. Uses only the .log for '
              'the eigenvalues and eigenvectors.'))
    data_args.add_argument(
        '-geigz2', type=str, nargs='+', action='append',
        default=[], metavar='somename.log,somename.fchk',
        help=('Gaussian eigenmatrix. Incluldes all elements, but zeroes '
              'all off-diagonal elements. Uses the .log for '
              'eigenvectors and .fchk for Hessian.'))
    data_args.add_argument(
        '-ma', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel angles (post-FF optimization).')
    data_args.add_argument(
        '-mb', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel bond lengths (post-FF optimization).')
    data_args.add_argument(
        '-me', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel energies (pre-FF optimization).')
    data_args.add_argument(
        '-meo', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel energies (post-FF optimization).')
    data_args.add_argument(
        '-mjeig', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae,somename.out',
        help='MacroModel eigenmatrix (all elements). Uses Jaguar '
        'eigenvectors.')
    data_args.add_argument(
        '-mgeig', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae,somename.out',
        help='MacroModel eigenmatrix (all elements). Uses Gaussian '
        'eigenvectors.')
    data_args.add_argument(
        '-mq', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel charges.')
    data_args.add_argument(
        '-mqh', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel charges (excludes aliphatic hydrogens).')
    data_args.add_argument(
        '-mt', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='MacroModel torsions (post-FF optimization).')
    data_args.add_argument(
        '-ja', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='Jaguar angles.')
    data_args.add_argument(
        '-jb', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='Jaguar bond lengths.')
    data_args.add_argument(
        '-je', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='Jaguar energies.')
    data_args.add_argument(
        '-jeo', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help=('Jaguar energies. Same as -je, except the files selected '
              'by this command will have their energies compared to those '
              'selected by -meo.'))
    data_args.add_argument(
        '-jeigz', type=str, nargs='+', action='append',
        default=[], metavar='somename.in,somename.out',
        help=('Jaguar eigenmatrix. Incluldes all elements, but zeroes '
              'all off-diagonal elements.'))
    data_args.add_argument(
        '-jq', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='Jaguar partial charges.')
    data_args.add_argument(
        '-jqh', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help=('Jaguar partial charges (excludes aliphatic hydrogens). '
              'Sums aliphatic hydrogen charges into their bonded sp3 '
              'carbon.'))
    data_args.add_argument(
        '-jt', type=str, nargs='+', action='append',
        default=[], metavar='somename.mae',
        help='Jaguar torsions.')
    data_args.add_argument(
        '-r', type=str, nargs='+', action='append',
        default=[], metavar='somename.txt',
        help='Read reference data from file.')
    return parser

def collect_data(coms, inps, direc='.', sub_names=['OPT']):
    # outs looks like:
    # {'filename1': <some class for filename1>,
    #  'filename2': <some class for filename2>,
    #  'filename3': <some class for filename3>
    # }
    outs = {}
    data = []
    for com, groups_filenames in coms.iteritems():
        # REFERENCE FILE
        if com == 'r':
            for group_filenames in groups_filenames:
                for filename in group_filenames:
                    data.extend(read_reference(os.path.join(direc, filename)))
        # JAGUAR ENERGIES
        if com in ['je', 'je2', 'jeo']:
            if com == 'je': typ = 'e'
            elif com == 'jeo': typ = 'eo'
            # Move through files. Grouping matters here. Each group (idx_1)
            # is used to separately calculate relative energies.
            for grp_num, group_filenames in enumerate(groups_filenames):
                for filename in group_filenames:
                    if filename not in outs:
                        outs[filename] = \
                            filetypes.Mae(os.path.join(direc, filename))
                    mae = outs[filename]
                    for str_num, struct in enumerate(mae.structures):
                        e = struct.props['r_j_Gas_Phase_Energy'] * \
                            co.HARTREE_TO_KJMOL
                        data.append(datatypes.Datum(
                                val=e,
                                com=com,
                                typ=typ,
                                src_1=filename,
                                idx_1=grp_num + 1,
                                idx_2=str_num + 1))
        # JAGUAR CHARGES
        if com in ['jq', 'jqh']:
            for group_filenames in groups_filenames:
                for filename in group_filenames:
                    if filename not in outs:
                        outs[filename] = filetypes.Mae(os.path.join(
                                directory, filename))
                    mae = outs[filename]
                    for i, structure in enumerate(mae.structures):
                        if com == 'jqh':
                            aliph_hyds = structure.get_aliph_hyds()
                            aliph_hyds_inds = [x.index for x in aliph_hyds]
                        for atom in structure.atoms:
                            # If it doesn't have the property b_q_use_charge,
                            # use it.
                            # If b_q_use_charge is 1, use it. If it's 0, don't
                            # use it.
                            if not 'b_q_use_charge' in atom.props or \
                                    atom.props['b_q_use_charge']:
                                q = atom.partial_charge
                                # If we're summing hydrogens into heavy atoms,
                                # start adding in those hydrogens.
                                if com == 'jqh':
                                    for bonded_atom_ind in \
                                            atom.bonded_atom_indices:
                                        if bonded_atom_ind in aliph_hyds_inds:
                                            q += structure.atoms[
                                                bonded_atom_ind - 
                                                1].partial_charge
                                if com == 'jq' or not atom in aliph_hyds:
                                    data.append(datatypes.Datum(
                                            val=q,
                                            com=com,
                                            typ='q',
                                            src_1=filename,
                                            idx_1=i+1,
                                            atm_1=atom.index))
        # MACROMODEL CHARGES
        if com in ['mq', 'mqh']:
            for group_filenames in groups_filenames:
                for filename in group_filenames:
                    # Get the corresponding output file for the given input.
                    mae = inps[filename].name_mae
                    if mae not in outs:
                        outs[mae] = filetypes.Mae(
                            os.path.join(inps[filename].directory, mae))
                    mae = outs[mae]
                    # Pick out the right structures. Sometimes our .com files
                    # generate many structures in a .mae, not all of which
                    # apply to this command.
                    structures = filetypes.select_structures(
                        mae.structures, inps[filename]._index_output_mae, 'pre')
                    for str_num, structure in structures:
                        if com == 'mqh':
                            aliph_hyds = structure.get_aliph_hyds()
                        for atom in structure.atoms:
                            if not 'b_q_use_charge' in atom.props or \
                                    atom.props['b_q_use_charge']:
                                # MacroModel by default makes the partial charge
                                # of aliphatic hydrogens zero, so we don't have
                                # to do any summation.
                                if com == 'mq' or not atom in aliph_hyds:
                                    data.append(datatypes.Datum(
                                            val=atom.partial_charge,
                                            com=com,
                                            typ='q',
                                            src_1=filename,
                                            idx_1=str_num + 1,
                                            atm_1=atom.index))
        # MACROMODEL ENERGIES
        if com in ['me', 'me2', 'meo']:
            if com == 'me': typ, ind = 'e', 'pre'
            elif com == 'meo': typ, ind = 'eo', 'opt'
            for grp_num, group_filenames in enumerate(groups_filenames):
                for filename in group_filenames:
                    if inps[filename].name_mae not in outs:
                        outs[inps[filename].name_mae] = \
                                 filetypes.Mae(os.path.join(
                                    inps[filename].directory,
                                    inps[filename].name_mae))
                    mae = outs[inps[filename].name_mae]
                    selected = filetypes.select_structures(
                        mae.structures, inps[filename]._index_output_mae, ind)
                    for str_num, struct in selected:
                        data.append(datatypes.Datum(
                                val=struct.props['r_mmod_Potential_Energy-MM3*'],
                                com=com,
                                typ=typ,
                                src_1=inps[filename].name_mae,
                                idx_1=grp_num + 1,
                                idx_2=str_num + 1))
        # SCHRODINGER STRUCTURES
        if com in ['ja', 'jb', 'jt', 'ma', 'mb', 'mt']:
            if com in ['ja', 'jb', 'jt']: index = 'pre'
            elif com in ['ma', 'mb', 'mt']: index = 'opt'
            if com in ['ja', 'ma']: typ = 'angles'
            elif com in ['jb', 'mb']: typ = 'bonds'
            elif com in ['jt', 'mt']: typ = 'torsions'
            # Move through files as you specified them on the command line.
            for group_filenames in groups_filenames:
                for filename in group_filenames:
                    # If 1st time accessing file, go ahead and do it. However,
                    # if you've already accessed it's data, don't read it again.
                    # Look it up in the dictionary instead.
                    if inps[filename].name_mmo not in outs:
                        outs[inps[filename].name_mmo] = \
                            filetypes.MacroModel(os.path.join(
                                inps[filename].directory,
                                inps[filename].name_mmo))
                    mmo = outs[inps[filename].name_mmo]
                    selected = filetypes.select_structures(
                        mmo.structures, inps[filename]._index_output_mmo, index)
                    for str_num, struct in selected:
                        data.extend(struct.select_stuff(
                                typ,
                                com=com,
                                com_match=sub_names,
                                src_1=mmo.filename,
                                idx_1=str_num + 1))
        # GAUSSIAN ENERGIES
        if com in ['ge', 'geo']:
            if com == 'ge': typ = 'e'
            elif com == 'geo': typ = 'eo'
            for grp_num, group_filenames in enumerate(groups_filenames):
                for name_log in group_filenames:
                    if name_log not in outs:
                        outs[name_log] = filetypes.GaussLog(
                            os.path.join(directory, name_log))
                    log = outs[name_log]
                    # Right now we're using the electronic energy plus
                    # the zero point correction.
                    hf = log.structures[0].props['hf']
                    zp = log.structures[0].props['zp']
                    energy = (hf + zp) * co.HARTREE_TO_KJMOL
                    data_list.append(
                        datatypes.Datum(
                            val=energy,
                            com=com,
                            typ=typ,
                            src_1=name_log,
                            idx_1=grp_num + 1))
        # GAUSSIAN EIGENMATRIX
        if com == 'geigz':
            for group_filenames in groups_filenames:
                for name_log in group_filenames:
                    if name_log not in outs:
                        outs[name_log] = filetypes.GaussLog(
                            os.path.join(directory, name_log))
                    log = outs[name_log]
                    evals = log.evals * co.HESSIAN_CONVERSION
                    evals_matrix = np.diag(evals)
                    low_tri_idx = np.tril_indices_from(evals_matrix)
                    lower_tri = evals_matrix[low_tri_idx]
                    data.extend([datatypes.Datum(
                                val=e,
                                com=com,
                                typ='eig',
                                src_1=name_log,
                                idx_1=x+1,
                                idx_2=y+1)
                                 for e, x, y in itertools.izip(
                                lower_tri, low_tri_idx[0], low_tri_idx[1])])
        # Kept this bit for legacy.
        if com == 'geigz2':
            for group_filenames in groups_filenames:
                for comma_filenames in group_filenames:
                    name_log, name_fchk = comma_filenames.split(',')
                    if name_log not in outs:
                        outs[name_log] = filetypes.GaussLog(
                            os.path.join(directory, name_log))
                    log = outs[name_log]
                    if name_fchk not in outs:
                        outs[name_fchk] = filetypes.GaussFormChk(
                            os.path.join(directory, name_fchk))
                    fchk = outs[name_fchk]
                    # I dislike how the Hessian is handled.
                    hess = datatypes.Hessian()
                    hess.hess = fchk.hess
                    hess.evecs = log.evecs
                    hess.atoms = fchk.atoms
                    hess.mass_weight_hessian()
                    hess.diagonalize()
                    # hess.mass_weight_eigenvectors()
                    diagonal_matrix = np.diag(np.diag(hess.hess))
                    low_tri_idx = np.tril_indices_from(diagonal_matrix)
                    lower_tri = diagonal_matrix[low_tri_idx]
                    data.extend([datatypes.Datum(
                                val=e,
                                com=com,
                                typ='eig',
                                src_1=name_log,
                                src_2=name_fchk,
                                idx_1=x+1,
                                idx_2=y+1)
                                 for e, x, y in itertools.izip(
                                lower_tri, low_tri_idx[0], low_tri_idx[1])])
        # MacroModel eigenmatrix for Gaussian QM data.
        if com == 'mgeig':
            for group_filenames in groups_filenames:
                for comma_filenames in group_filenames:
                    name_mae, name_gau_log = comma_filenames.split(',')
                    # Get the output log filename.
                    name_macro_log = inps[name_mae].name_log
                    if name_macro_log not in outs:
                        outs[name_macro_log] = filetypes.MacroModelLog(
                            os.path.join(inps[name_mae].directory,
                                         inps[name_mae].name_log))
                    macro_log = outs[name_macro_log]
                    if name_gau_log not in outs:
                        outs[name_gau_log] = filetypes.GaussLog(
                            os.path.join(directory, name_gau_log))
                    gau_log = outs[name_gau_log]
                    # Change how Hessian is handled.
                    hess = datatypes.Hessian()
                    hess.hess = macro_log.hessian
                    # Eigenvectors should already be mass weighted.
                    hess.evecs = gau_log.evecs
                    hess.diagonalize()
                    low_tri_idx = np.tril_indices_from(hess.hess)
                    lower_tri = hess.hess[low_tri_idx]
                    data.extend([datatypes.Datum(
                                val=e,
                                com=com,
                                typ='eig',
                                src_1=name_macro_log,
                                src_2=name_gau_log,
                                idx_1=x+1,
                                idx_2=y+1)
                                 for e, x, y in itertools.izip(
                                lower_tri, low_tri_idx[0], low_tri_idx[1])])
        # Schrodinger eigenmatrix
        if com in ['jeigz', 'mjeig']:
            for group_filenames in groups_filenames:
                for comma_filenames in group_filenames:
                    name_other, name_out = comma_filenames.split(',')
                    # For MacroModel, name_other is a .mae.
                    if com == 'mjeig':
                        # Get the .log for that .mae.
                        name_log = inps[name_other].name_log
                        if name_other not in outs:
                            outs[name_log] = filetypes.MacroModelLog(
                                os.path.join(inps[name_other].directory,
                                             inps[name_other].name_log))
                        # Here, other is the MacroModel .log.
                        other = outs[name_log]
                    # For Jaguar, name_other is a .in.
                    elif com == 'jeigz':
                        # Use the .in directly.
                        if name_other not in outs:
                            outs[name_other] = filetypes.JaguarIn(
                                os.path.join(direc, name_other))
                        # Here, other is the Jaguar .in.
                        other = outs[name_other]
                    # Both use the .out file, name_out.
                    if name_out not in outs:
                        outs[name_out] = filetypes.JaguarOut(os.path.join(
                                direc, name_out))
                    out = outs[name_out]
                    # This datatype can handle taking 
                    hess = datatypes.Hessian(other, out)
                    # We have to mass weight the Jaguar Hessian.
                    if com == 'jeigz':
                        hess.mass_weight_hessian()
                    hess.mass_weight_eigenvectors()
                    hess.diagonalize()
                    if com == 'jeigz':
                        # Funny way to set all elements besides the diagonal
                        # to zero.
                        diagonal_matrix = np.diag(np.diag(hess.hess))
                    else:
                        diagonal_matrix = hess.hess
                    low_tri_idx = np.tril_indices_from(diagonal_matrix)
                    lower_tri = diagonal_matrix[low_tri_idx]
                    data.extend([datatypes.Datum(
                            val=e,
                            com=com,
                            typ='eig',
                            src_1=name_other,
                            src_2=name_out,
                            idx_1=x+1,
                            idx_2=y+1)
                            for e, x, y in itertools.izip(
                            lower_tri, low_tri_idx[0], low_tri_idx[1])])
    logger.log(15, 'TOTAL DATA POINTS: {}'.format(len(data)))
    return data

def sort_commands_by_filename(commands):
    '''
    Takes a dictionary of commands like...

     {'me': [['a1.01.mae', 'a2.01.mae', 'a3.01.mae'], ['b1.01.mae', 'b2.01.mae']],
      'mb': [['a1.01.mae'], ['b1.01.mae']],
      'jeig': [['a1.01.in,a1.out', 'b1.01.in,b1.out']]
     }
    
    ... and turn it into a dictionary that looks like...

    {'a1.01.mae': ['me', 'mb'],
     'a1.01.in': ['jeig'],
     'a1.out': ['jeig'],
     'a2.01.mae': ['me'],
     'a3.01.mae': ['me'],
     'b1.01.mae': ['me', 'mb'],
     'b1.01.in': ['jeig'],
     'b1.out': ['jeig'],
     'b2.01.mae': ['me']
    }

    Arguments
    ---------
    commands : dic

    Returns
    -------
    dictionary of the sorted commands
    '''
    sorted_commands = {}
    for command, groups_filenames in commands.iteritems():
        for comma_separated in itertools.chain.from_iterable(
            groups_filenames):
            for filename in comma_separated.split(','):
                if filename in sorted_commands:
                    sorted_commands[filename].append(command)
                else:
                    sorted_commands[filename] = [command]
    return sorted_commands
            
def read_reference(filename):
    data = []
    with open(filename, 'r') as f:
        for line in f:
            # Skip certain lines.
            if line.startswith('-'):
                continue
            # Remove everything following a # in a line.
            line = line.partition('#')[0]
            cols = line.split()
            # There should always be 3 columns.
            if len(cols) == 3:
                lbl, wht, val = cols
                datum = datatypes.Datum(lbl=lbl, wht=float(wht), val=float(val))
                lbl_to_data_attrs(datum, lbl)
                data.append(datum)
    return data

def lbl_to_data_attrs(datum, lbl):
    parts = lbl.split('_')
    datum.typ = parts[0]
    if len(parts) == 3:
        idxs = parts[-1]
    if len(parts) == 4:
        idxs = parts[-2]
        atm_nums = parts[-1]
        atm_nums = atm_nums.split('-')
        for i, atm_num in enumerate(atm_nums):
            setattr(datum, 'atm_{}'.format(i+1), int(atm_num))
    idxs = idxs.split('-')
    datum.idx_1 = int(idxs[0])
    if len(idxs) == 2:
        datum.idx_2 == int(idxs[1])

def pretty_commands_for_files(commands_for_files, log_level=5):
    """
    Logs the .mae commands dictionary, or the all of the commands
    used on a particular file.

    Arguments
    ---------
    commands_for_files : dic
    log_level : int
    """
    if logger.getEffectiveLevel() <= log_level:
        foobar = textwrap.TextWrapper(
            width=48, subsequent_indent=' '*26)
        logger.log(
            log_level,
            '--' + ' FILENAME '.center(22, '-') +
            '--' + ' COMMANDS '.center(22, '-') +
            '--')
        for filename, commands in commands_for_files.iteritems():
            foobar.initial_indent = '  {:22s}  '.format(filename)
            logger.log(log_level, foobar.fill(' '.join(commands)))
        logger.log(log_level, '-'*50)

def pretty_all_commands(commands, log_level=5):
    """
    Logs the arguments/commands given to calculate that are used
    to request particular datatypes from particular files.

    Arguments
    ---------
    commands : dic
    log_level : int
    """
    if logger.getEffectiveLevel() <= log_level:
        foobar = textwrap.TextWrapper(width=48, subsequent_indent=' '*24)
        logger.log(
            log_level,
            '--' + ' COMMAND '.center(9, '-') +
            '--' + ' GROUP # '.center(9, '-') +
            '--' + ' FILENAMES '.center(24, '-') + 
            '--')
        for command, groups_filenames in commands.iteritems():
            for i, filenames in enumerate(groups_filenames):
                if i == 0:
                    foobar.initial_indent = \
                        '  {:9s}  {:^9d}  '.format(command, i+1)
                else:
                    foobar.initial_indent = \
                        '  ' + ' '*9 + '  ' + '{:^9d}  '.format(i+1)
                logger.log(log_level, foobar.fill(' '.join(filenames)))
        logger.log(log_level, '-'*50)

def pretty_data(data, log_level=20):
    """
    Logs data as a table.

    Arguments
    ---------
    data : list of Datum
    log_level : int
            Logging level used.
    """
    if data[0].wht:
        string = ('--' + ' LABEL '.center(22, '-') +
                  '--' + ' WEIGHT '.center(22, '-') +
                  '--' + ' VALUE '.center(22, '-') + '--')
    else:
        string = ('--' + ' LABEL '.center(22, '-') +
                  '--' + ' VALUE '.center(22, '-') + '--')
    if log_level:
        logger.log(log_level, string)
    else:
        print(string)
    for d in data:
        if d.wht:
            string = ('  ' + '{:22s}'.format(d.lbl) +
                      '  ' + '{:22.4f}'.format(d.wht) + 
                      '  ' + '{:22.4f}'.format(d.val))
        else:
            string = ('  ' + '{:22s}'.format(d.lbl) +
                      '  ' + '{:22.4f}'.format(d.val))
        if log_level:
            logger.log(log_level, string)
        else:
            print(string)
    if log_level:
        logger.log(log_level, '-' * 50)

if __name__ == '__main__':
    logging.config.dictConfig(co.LOG_SETTINGS)
    main(sys.argv[1:])
