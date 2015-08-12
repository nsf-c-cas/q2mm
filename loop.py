import argparse
import itertools
import logging
import logging.config
import os
import random
import sys

import calculate
import constants as co
import compare
import datatypes
import optimizer
import parameters

logger = logging.getLogger(__name__)

class Loop(object):
    def __init__(self):
        self.convergence = 0.01
        self.current_cycle_num = 0
        self.ff = None
        self.ff_args = None
        self.ff_lines = None
        self.loop_lines = None
        self.ref_args = None
        # Unnecessary if we keep self.ff as an attribute. self.ff and
        # self.score shouldn't ever be different.
        self.score = None
        self.score_init = None
        self.score_prev = None
    def opt_loop(self):
        change = None
        while self.score_prev is None \
                or change is None \
                or change > self.convergence:
            self.current_cycle_num += 1
            self.score_prev = self.score
            self.score = self.run_loop_input(self.loop_lines, score=self.score)
            change = (self.score_prev - self.score) / self.score_prev
            logger.log(20, ' Cycle {} Summary '.format(
                    self.current_cycle_num).center(50, '-'))
            logger.log(20, '| PF Score: {:36.15f} |'.format(self.score))
            logger.log(20, '| % change: {:36.15f} |'.format(change))
            logger.log(20, '-' * 50)
        return self.score
    def run_loop_input(self, lines, score=None):
        if score:
            self.score = score
        lines_iterator = iter(lines)
        while True:
            try:
                line = lines_iterator.next()
            except StopIteration:
                return self.score
            cols = line.split()
            if cols[0] == 'FFLD':
                # Import FF data.
                if cols[1] == 'read':
                    self.ff = datatypes.import_ff(cols[2])
                    with open(cols[2], 'r') as f:
                        self.ff_lines = f.readlines()
                # Export FF data.
                if cols[1] == 'write':
                    datatypes.export_ff(cols[2], self.ff.params, lines=self.ff_lines)
            # Trim parameters.
            if cols[0] == 'PARM':
                self.ff.params = parameters.trim_params_by_file(
                    self.ff.params, cols[1])
            if cols[0] == 'LOOP':
                logger.log(20, ' Optimization Loop '.center(50, '='))
                # Read lines that will be looped over.
                loop_lines = []
                line = lines_iterator.next()
                while line.split()[0] != 'END':
                    loop_lines.append(line)
                    line = lines_iterator.next()
                # Make loop object and populate.
                loop = Loop()
                loop.convergence = float(cols[1])
                loop.loop_lines = loop_lines
                loop.score = self.score
                # Log commands.
                logger.log(20, 'Commands:')
                for loop_line in loop_lines:
                    logger.log(20, '> ' + loop_line)
                logger.log(20,'Initial PF Score: {}'.format(self.score))
                logger.log(20, '=' * 50)            
                self.score = loop.opt_loop()
            if cols[0] == 'RDAT':
                logger.log(20, 'Calculating reference data...')
                self.ref_args = ' '.join(cols[1:]).split()
                ref_conn = calculate.main(self.ref_args)
            if cols[0] == 'CDAT':
                logger.log(20, 'Calculating force field data...')
                self.ff_args = ' '.join(cols[1:]).split()
                cal_conn = calculate.main(self.ff_args)
            if cols[0] == 'COMP':
                if '-o' in cols:
                    output_filename = cols[cols.index('-o') + 1]
                    self.score, output_string = compare.compare_data(
                        ref_conn, cal_conn, pretty=True)
                    with open(output_filename, 'w') as f:
                        for output_line in output_string:
                            f.write(output_line+ '\n')
                else:
                    self.score = compare.compare_data(ref_conn, cal_conn)
            if cols[0] == 'GRAD':
                grad = optimizer.Gradient(
                    ff=self.ff, ff_args=self.ff_args, ff_lines=self.ff_lines,
                    ref_conn=ref_conn)
                self.ff = grad.run()
                self.score = self.ff.score
            # if cols[0] == 'SIMP':
            #     score = simplex(score)

def read_loop_input(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()
    lines = [x.partition('#')[0].strip('\n') for x in lines if
             x.partition('#')[0].strip('\n') != '']
    logger.log(20, ' Q2MM '.center(79, '='))
    logger.log(20, 'Commands:')
    for line in lines:
        logger.log(20, '> ' + line)
    logger.log(20, '=' * 79)
    return lines


# def simplex(score):
#     logger.log(20, 'Running simplex optimization...')
#     new_change = random.uniform(0, score)
#     new_scale = abs(random.gauss(0, 0.1))
#     while new_scale > 1:
#         new_scale = abs(random.gauss(0, 0.1))
#     score = score - new_change * new_scale
#     logger.log(20, 'PF Score: {}'.format(score))
#     return score

def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'input', type=str, help='Filename containing loop commands.')
    opts = parser.parse_args(args)
    lines = read_loop_input(opts.input)
    loop = Loop()
    loop.run_loop_input(lines)

if __name__ == '__main__':
    # if os.path.isfile('root.log'):
    #     os.remove('root.log')
    logging.config.dictConfig(co.LOG_SETTINGS)
    main(sys.argv[1:])
