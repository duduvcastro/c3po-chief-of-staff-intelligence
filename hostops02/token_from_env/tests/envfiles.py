"""The environment files of the token placement's tests: the files the parser accepts and the files it refuses, rule by
rule, and a deterministic generator of more files of the same kinds. Shared by tests/test_token_from_env.py (the parser
on the workstation) and linux_root/token_shape.py (what the runner's docker compose makes of the same files). No pytest
here: the proof script imports this module as root with the interpreter of the distribution.

Every token is fake. T is the main fake token of tok.py; L is the literal fake value of the task."""
import random

import tok

T=tok.TOKEN.encode();L=tok.LITERAL.encode();GOOD=T+b'\n'
HIDDEN=b'FaKeHiDdEnVaLuEfOrTeStS'                    # a second fake value, where a file would hide one
OTHER_VALUE=b'FaKeOtHeRvAlUeFoRtEsTs'

# (name, file); each yields GOOD (the main fake token and a newline) unless named in SPECIAL_VALUES
ACCEPTED_FILES=[
    ('plain',b'MASSIVE_API_TOKEN='+T+b'\n'),
    ('no_final_newline',b'MASSIVE_API_TOKEN='+T),
    ('the_literal_fake_value',b'MASSIVE_API_TOKEN='+L+b'\n'),
    ('c3po_name',b'C3PO_MASSIVE_API_TOKEN='+T+b'\n'),
    ('both_names_equal',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'\n'),
    ('twice_equal',b'MASSIVE_API_TOKEN='+T+b'\nX=1\nMASSIVE_API_TOKEN='+T+b'\n'),
    ('every_other_form_of_other_names',b'# a comment\n\n  \t\n   # indented comment with \xc3\xa9 and \xe2\x80\x9cquotes\xe2\x80\x9d\n'
        b'OTHER="quoted value # not a comment $NOT"\nOTHER2=\'single $x "y"\'\nexport OTHER3=1\nOTHER4: yaml style\n  OTHER5 = spaced  # comment\n'
        b'OTHER6=value with spaces # and a comment\nOTHER7=S\xc3\xa3o Paulo\nOTHER8=\nOTHER9="" \nOTHER.A-B[0]=x\n'
        b'OTHER10="a" # c\nOTHER11=\'b\'\t\nexport\tOTHER12=1\nexport=1\nexportOTHER=1\nOTHER13=\'"\'\n'
        b'MASSIVE_API_TOKEN='+T+b'\n#MASSIVE_API_TOKEN=commented-out-value\n  # massive_api_token=x\n'),
    ('backslashes_in_quoted_values_of_other_names',b'PEM="-----BEGIN KEY-----\\nabc\\n-----END KEY-----"\nWINDOWS=\'C:\\Users\\x\'\n'
        b'SAID="it\\\'s"\nTAB="a\\tb" # comment\nMASSIVE_API_TOKEN='+T+b'\n'),
    ('names_that_resemble_the_name',b'MASSIVE.API.TOKEN=z\nMASSIVE_API_KEY=x\nMASSIVEAPITOKEN=w\nC3PO_MASSIVE_PLAN=stocks-advanced\n'
        b'MASSIVE_API_TOKEN='+T+b'\n'),
    ('the_release_example_filled',b'BRAPI_TOKEN=\nC3PO_BRAPI_PLAN=pro\nEODHD_API_TOKEN=\nMASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_PLAN=stocks-advanced\n'
        b'C3PO_MASSIVE_FLAT_FILES_ACCESS_KEY=\nC3PO_MASSIVE_FLAT_FILES_SECRET_KEY=\n# C3PO_DAY_D_DATA_MOUNT_SOURCE=/mnt/day-d-data\n'
        b'C3PO_DAY_D_DATA_MOUNT_SOURCE=c3po_day_d_data\n'),
    ('sixteen_characters',b'MASSIVE_API_TOKEN='+b'Ab'*8),
    ('five_hundred_and_twelve_characters',b'MASSIVE_API_TOKEN='+b'Ab'*256+b'\n'),
    ('every_character_of_the_grammar',b'C3PO_MASSIVE_API_TOKEN=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~+/=-\n'),
]
SPECIAL_VALUES={'the_literal_fake_value':L,'sixteen_characters':b'Ab'*8,'five_hundred_and_twelve_characters':b'Ab'*256,
                'every_character_of_the_grammar':b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~+/=-'}
def value_of(name):
    """The value (without the newline) an accepted file of the list yields."""
    return SPECIAL_VALUES.get(name,T)

# (name, file, constant code)
REFUSED_FILES=[
    # the file
    ('carriage_return_line_ends',b'MASSIVE_API_TOKEN='+T+b'\r\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('carriage_return_elsewhere',b'A=1\r\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('nul_byte',b'A=\x00\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('byte_order_mark',b'\xef\xbb\xbfMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('no_break_space_before_a_name',b'\xc2\xa0A=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('vertical_tab_before_a_name',b'\x0bA=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('form_feed_line',b'\x0c\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('non_ascii_name',b'CAF\xc3\x89=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('the_name_with_a_kelvin_sign',b'MASSIVE_API_TOKEN='+T+b'\nMASSIVE_API_TO\xe2\x84\xaaEN='+HIDDEN+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('name_with_a_space',b'FOO BAR=1\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('a_line_of_punctuation',b'!!!\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('a_quoted_line',b'"A=1"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    # a name without "=" or ":" (compose v2 takes it from its own environment; an older parser took the next line)
    ('a_name_without_a_value',b'INHERITED\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('export_of_a_name_without_a_value',b'export INHERITED2\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('export_alone',b'export\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('taken_from_the_environment_of_compose',b'MASSIVE_API_TOKEN\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('export_taken_from_the_environment',b'MASSIVE_API_TOKEN='+T+b'\nexport C3PO_MASSIVE_API_TOKEN\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    # values of other names whose end is not the same in every parser
    ('quoted_value_over_two_lines_hiding_a_definition',b'MASSIVE_API_TOKEN='+T+b'\nOTHER="abc\nMASSIVE_API_TOKEN='+HIDDEN+b'\n"\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('single_quoted_value_over_two_lines',b"OTHER='abc\ndef'\nMASSIVE_API_TOKEN="+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('quoted_value_with_a_backslash_before_the_quote',b'OTHER="a\\"b"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('single_quoted_value_with_a_backslash_before_the_quote',b"OTHER='a\\'b'\nMASSIVE_API_TOKEN="+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('an_escaped_quote_followed_by_what_looks_like_a_comment',b'OTHER="a\\" # c"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('an_escaped_single_quote_followed_by_spaces',b"OTHER='a\\'  \nMASSIVE_API_TOKEN="+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('quoted_value_ending_in_two_backslashes',b'OTHER="ab\\\\"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('quoted_value_with_two_backslashes_inside',b'OTHER="a\\\\b"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('a_statement_after_a_closing_quote',b'OTHER="x" MASSIVE_API_TOKEN='+HIDDEN+b'\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('text_after_a_closing_quote',b"OTHER='x'y\nMASSIVE_API_TOKEN="+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_a_vertical_tab',b'OTHER=\x0b"a\nb"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_a_form_feed',b'OTHER=\x0cx\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('unquoted_value_beginning_with_a_vertical_tab',b'OTHER=\x0bx\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('unclosed_quote_alone',b'OTHER="\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('unclosed_quote_with_a_comment_sign',b'OTHER=\'#x\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_a_no_break_space_and_a_quote',b'OTHER=\xc2\xa0"a\nMASSIVE_API_TOKEN='+HIDDEN+b'\n"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    ('value_beginning_with_another_non_ascii_byte',b'OTHER=\xe3\x80\x80x\nMASSIVE_API_TOKEN='+T+b'\n','ENV_FILE_SYNTAX_UNSUPPORTED'),
    # a definition that is not the plain form
    ('export',b'export MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('export_with_a_tab',b'export\tC3PO_MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('leading_space',b' MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('leading_tab',b'\tMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('space_before_the_sign',b'MASSIVE_API_TOKEN ='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('space_after_the_sign',b'MASSIVE_API_TOKEN= '+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('tab_after_the_sign',b'MASSIVE_API_TOKEN=\t'+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('colon',b'MASSIVE_API_TOKEN: '+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('colon_without_space',b'MASSIVE_API_TOKEN:'+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('lower_case',b'massive_api_token='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('mixed_case',b'MASSIVE_API_TOKEN='+T+b'\nMassive_Api_Token='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    ('lower_case_c3po',b'MASSIVE_API_TOKEN='+T+b'\nc3po_massive_api_token='+T+b'\n','ENV_TOKEN_DEFINITION_NOT_PLAIN'),
    # the name anywhere but as a plain definition or in a comment
    ('a_definition_after_a_tab_in_a_value',b'MASSIVE_API_TOKEN='+T+b'\nA=b\tMASSIVE_API_TOKEN='+HIDDEN+b'\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('a_definition_after_a_space_in_a_value',b'A=b MASSIVE_API_TOKEN='+HIDDEN+b'\nMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('the_name_in_a_value',b'MASSIVE_API_TOKEN='+T+b'\nOTHER=${MASSIVE_API_TOKEN}\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('the_name_in_a_quoted_value',b'OTHER="see MASSIVE_API_TOKEN"\nMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('the_name_in_lower_case_in_a_value',b'MASSIVE_API_TOKEN='+T+b'\nOTHER=massive_api_token\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('the_name_with_a_kelvin_sign_in_a_value',b'MASSIVE_API_TOKEN='+T+b'\nOTHER=MASSIVE_API_TO\xe2\x84\xaaEN\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('a_longer_name',b'MASSIVE_API_TOKEN_OLD=FaKeOlDvAlUeFoRtEsTs\nMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('a_prefixed_longer_name',b'MASSIVE_API_TOKEN='+T+b'\nOLD_MASSIVE_API_TOKEN=x\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('a_name_with_a_digit_after_it',b'MASSIVE_API_TOKEN='+T+b'\nMASSIVE_API_TOKEN2=y\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('a_c3po_name_with_a_suffix',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN_X=w\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    ('the_name_in_a_value_of_another_case',b'MASSIVE_API_TOKEN='+T+b'\nOTHER=Massive_Api_Token\n','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION'),
    # no definition
    ('empty_file',b'','ENV_TOKEN_ABSENT'),
    ('only_other_names',b'C3PO_DB_PASSWORD=x\nEODHD_API_TOKEN=y\n','ENV_TOKEN_ABSENT'),
    ('commented_out',b'# MASSIVE_API_TOKEN='+T+b'\n#C3PO_MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_ABSENT'),
    # definitions that disagree
    ('two_names_two_values',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+OTHER_VALUE+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('one_name_twice_two_values',b'MASSIVE_API_TOKEN='+OTHER_VALUE+b'\nMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('third_definition_disagrees',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'\nMASSIVE_API_TOKEN='+OTHER_VALUE+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('one_value_a_prefix_of_the_other',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'x\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('one_letter_of_another_case',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T.swapcase()+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('an_empty_and_a_good_one',b'MASSIVE_API_TOKEN=\nC3PO_MASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    ('the_template_line_and_a_filled_one',b'MASSIVE_API_TOKEN=\nMASSIVE_API_TOKEN='+T+b'\n','ENV_TOKEN_DEFINITIONS_DISAGREE'),
    # the value (every defect of it has the one code, whatever its first byte)
    ('empty_value',b'MASSIVE_API_TOKEN=\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('fifteen_characters',b'MASSIVE_API_TOKEN='+b'Ab'*7+b'A\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('five_hundred_and_thirteen_characters',b'MASSIVE_API_TOKEN='+b'Ab'*256+b'A\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('double_quoted',b'MASSIVE_API_TOKEN="'+T+b'"\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('single_quoted',b"MASSIVE_API_TOKEN='"+T+b"'\n",'ENV_TOKEN_VALUE_GRAMMAR'),
    ('an_unclosed_quote',b'MASSIVE_API_TOKEN="'+T+b'\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_closing_quote_and_a_statement',b'MASSIVE_API_TOKEN="'+T+b'" OTHER=x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('beginning_with_a_vertical_tab',b'MASSIVE_API_TOKEN=\x0b'+T+b'\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('beginning_with_a_non_ascii_byte',b'MASSIVE_API_TOKEN=\xc3\xa9'+T+b'\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('beginning_with_a_no_break_space',b'MASSIVE_API_TOKEN=\xc2\xa0'+T+b'\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('trailing_space',b'MASSIVE_API_TOKEN='+T+b' \n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('trailing_tab',b'MASSIVE_API_TOKEN='+T+b'\t\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('inline_comment',b'MASSIVE_API_TOKEN='+T+b' # the token\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_hash_inside',b'MASSIVE_API_TOKEN='+T+b'#x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_variable',b'MASSIVE_API_TOKEN=$OTHER_VALUE_FOR_TESTS\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_braced_variable',b'MASSIVE_API_TOKEN='+T+b'${X}\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_backslash',b'MASSIVE_API_TOKEN='+T+b'\\n\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_space_inside',b'MASSIVE_API_TOKEN=FaKe ToKeNfOrTeStSoNlY\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_non_ascii_letter',b'MASSIVE_API_TOKEN='+T+b'\xc3\xa9\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_quote_inside',b'MASSIVE_API_TOKEN='+T+b'"x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('an_at_sign',b'MASSIVE_API_TOKEN='+T+b'@x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_comma',b'MASSIVE_API_TOKEN='+T+b',x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_colon',b'MASSIVE_API_TOKEN='+T+b':x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_semicolon',b'MASSIVE_API_TOKEN='+T+b';x\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('a_backtick',b'MASSIVE_API_TOKEN='+T+b'`x`\n','ENV_TOKEN_VALUE_GRAMMAR'),
    ('the_literal_fake_value_quoted',b'MASSIVE_API_TOKEN="'+L+b'"\n','ENV_TOKEN_VALUE_GRAMMAR'),
]


# ---------------------------------------------------------------- more files of the same kinds, from a fixed seed
OTHER_NAMES=[b'A',b'OTHER',b'C3PO_DB_PASSWORD',b'EODHD_API_TOKEN',b'X.Y',b'L[0]',b'a-b',b'exportX',b'export',b'MASSIVE.API.TOKEN',b'MASSIVE_API_KEY']
PIECES=[b'x',b'value',b' ',b'\t',b'#',b' #',b'$X',b'${Y}',b'"',b"'",b'\\n',b'\\t',b'\\',b'=',b':',b'\xc3\xa9',b'\xc2\xa0',b'S\xc3\xa3o',b'-',b'.',b'/',b'~']
def _value(r):
    """A value of another name, of any of the forms a hand-edited file holds."""
    kind=r.random();body=b''.join(r.choice(PIECES) for _ in range(r.randint(0,5)))
    if kind<0.4:return body
    quote=r.choice([b'"',b"'"]);inner=body.replace(quote,b'')
    tail=r.choice([b'',b'',b' ',b'\t',b' # c',b'  #c',b'x',b' y=1'])
    return quote+inner+quote+tail
def _other_line(r):
    lead=r.choice([b'',b'',b'',b' ',b'\t',b'export ',b'export\t',b'  export '])
    space=r.choice([b'',b'',b' ',b'\t']);separator=r.choice([b'=',b'=',b'=',b':']);gap=r.choice([b'',b'',b' ',b'\t'])
    return lead+r.choice(OTHER_NAMES)+space+separator+gap+_value(r)
def _comment(r):return r.choice([b'',b' ',b'\t'])+b'#'+r.choice([b'',b' comment',b' MASSIVE_API_TOKEN=old',b'massive_api_token',b' "unclosed'])
def generated(seed,count):
    """[(name, file, value)]: count files of other names, comments and blanks around one or more plain definitions
    of the main fake token (each name, both names, the same name twice), in a fixed order from the seed."""
    r=random.Random(seed);out=[]
    for index in range(count):
        lines=[]
        for _ in range(r.randint(0,7)):
            kind=r.random()
            lines.append(_other_line(r) if kind<0.7 else _comment(r) if kind<0.85 else r.choice([b'',b' ',b'\t ']))
        definitions=r.choice([[b'MASSIVE_API_TOKEN'],[b'C3PO_MASSIVE_API_TOKEN'],[b'MASSIVE_API_TOKEN',b'C3PO_MASSIVE_API_TOKEN'],
                              [b'MASSIVE_API_TOKEN',b'MASSIVE_API_TOKEN']])
        for key in definitions:lines.insert(r.randint(0,len(lines)),key+b'='+T)
        out.append(('generated_%04d'%index,b'\n'.join(lines)+r.choice([b'',b'\n']),T))
    return out
