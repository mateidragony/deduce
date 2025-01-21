#
# The checking process for programs & proofs has three steps:
#
# 1. process_declarations:
#    Collects the type environment for the top-level statements, usually
#    from their declared types. (Except for define's without types.)
#
# 2. type_check_stmt:
#    Type check the bodies of functions using the type environment.
#    Perform overload resolution using the types.
#
# 3. collect_env:
#    Collects the proofs (mapping proof labels to their formulas
#              and runtime environment mapping variables to values)
#    and the values (mapping names to their values, for defines a functions)
#    into an environment.
#
# 4. check_proofs:
#    Check that the proofs follow the rules of logic
#    and run the print and assert statements.

from abstract_syntax import *
from error import error, incomplete_error, warning, error_header, get_verbose, set_verbose, IncompleteProof, VerboseLevel

imported_modules = set()
checked_modules = set()

name_id = 0

def generate_name(name):
    global name_id
    ls = name.split('.')
    new_id = name_id
    name_id += 1
    return ls[0] + '.' + str(new_id)
  
def check_implies(loc, frm1, frm2):
  if get_verbose():
    print('check_implies? ' + str(frm1) + ' => ' + str(frm2))
  match (frm1, frm2):
    case (_, Bool(loc2, tyof2, True)):
      return
  
    case (_, And(loc2, tyof2, args)):
      try:
        for arg2 in args:
          check_implies(loc, frm1, arg2)
      except Exception as e:
          msg = str(e) + '\n\nWhile trying to prove that\n\t' + str(frm1) \
              + '\nimplies\n'\
              + '\t' + str(frm2)
          raise Exception(msg)
        
    case(Or(loc1, tyof1, args1), _):
      for arg1 in args1:
        try:
          check_implies(loc, arg1, frm2)
        except Exception as e:
          msg = str(e) + '\n\nWhile trying to prove that\n\t' + str(frm1) \
              + '\nimplies\n'\
              + '\t' + str(frm2)
          raise Exception(msg)
      
    case (Bool(loc2, tyof2, False), _):
      return
  
    case (And(loc2, tyof2, args1), _):
      for arg1 in args1:
        try:
          check_implies(loc, arg1, frm2)
          return
        except Exception as e:
          # implicit modus ponens
          match arg1:
            case IfThen(loc3, tyof3, prem, conc):
              try:
                  check_implies(loc, conc, frm2)
                  rest = And(loc2, tyof2, [arg for arg in args1 if arg != arg1])
                  check_implies(loc, rest, prem)
                  return
              except Exception as e2:
                  pass
            case _:
              pass
          continue
      error(loc, '\nCould not prove that\n\t' + str(frm1) + '\n' \
            + 'implies\n\t' + str(frm2) + '\n' \
            + 'because we could not prove at least one of\n'
            + '\n'.join(['\t' + str(arg1) + '   implies   ' + str(frm2)\
                         for arg1 in args1]))
            
    case (_, Or(loc2, tyof2, args2)):
      for arg2 in args2:
        try:
          check_implies(loc, frm1, arg2)
          return
        except Exception as e:
          continue
      error(loc, '\nCould not prove that\n\t' + str(frm1) + '\n' \
            + 'implies\n\t' + str(frm2) + '\n' \
            + 'because we could not prove at least one of\n'
            + '\n'.join(['\t' + str(frm1) + '   implies   ' + str(arg2)\
                         for arg2 in args2]))
      
    case (IfThen(loc1, tyof1, prem1, conc1), IfThen(loc2, tyof2, prem2, conc2)):
      try:
        check_implies(loc, prem2, prem1)
        check_implies(loc, conc1, conc2)
      except Exception as e:
        msg = str(e) + '\n\nWhile trying to prove that\n\t' + str(frm1) \
            + '\nimplies\n'\
            + '\t' + str(frm2)
        raise Exception(msg)
      
    case (All(loc1, tyof1, var1, _, body1), All(loc2, tyof2, var2, _, body2)):
      try:
          sub = { var2[0]: Var(loc2, var1[1], var1[0], []) }
          body2a = body2.substitute(sub)
          check_implies(loc, body1, body2a)
      except Exception as e:
        msg = str(e) + '\n\nWhile trying to prove that\n\t' + str(frm1) \
            + '\nimplies\n'\
            + '\t' + str(frm2)
        raise Exception(msg)

    case (All(loc1, tyof1, vars1, _, body1), _):
       matching = {}
       try:
         #print('*** trying to instantiate\n\t' + str(frm1) + '\nto\n\t' + str(frm2))
         vars, body = collect_all(frm1)
         formula_match(loc, vars, body, frm2, matching, Env())
       except Exception as e:
         error(loc, '\nCould not prove that\n\t' + str(frm1) \
                  + '\ninstantiates to\n\t' + str(frm2) \
               + '\nbecause ' + str(e))
       
    case _:
      if frm1 != frm2:
        (small_frm1, small_frm2) = isolate_difference(frm1, frm2)
        if small_frm1 != frm1:
            msg = 'error, the proved formula:\n' \
                + '\t' + str(frm1) + '\n' \
            + 'does not match the goal:\n' \
            + '\t' + str(frm2) + '\n' \
            + 'because\n\t' + str(small_frm1) + '\n\t≠ ' + str(small_frm2) + '\n' 
            error(loc, msg)
        else:
            error(loc, '\nCould not prove that\n\t' + str(frm1) \
                  + '\nimplies\n\t' + str(frm2))

def instantiate(loc, allfrm, arg):
  match allfrm:
    case All(loc2, tyof, (var, ty), (s, e), frm):
      sub = { var : arg }
      ret = frm.substitute(sub)
      if s != 0:
        ret = update_all_head(ret)
      return ret
    case _:
      error(loc, 'expected all formula to instantiate, not ' + str(allfrm))
  
def str_of_env(env):
  return '{' + ', '.join([k + ": " + str(e) for (k,e) in env.items()]) + '}'

def pattern_to_term(pat):
  match pat:
    case PatternCons(loc, constr, params):
      if len(params) > 0:
        ret = Call(loc, None, constr,
                   [Var(loc, None, param, [param]) for param in params])
        return ret
      else:
        return constr
    case _:
      error(pat.location, "expected a pattern, not " + str(pat))

num_rewrites = 0

def reset_num_rewrites():
    global num_rewrites
    num_rewrites = 0

def inc_rewrites():
    global num_rewrites
    num_rewrites = 1 + num_rewrites

def get_num_rewrites():
    global num_rewrites
    return num_rewrites

def rewrite(loc, formula, equation):
    num_marks = count_marks(formula)
    if num_marks == 0:
        return rewrite_aux(loc, formula, equation)
    elif num_marks == 1:
        try:
            find_mark(formula)
            error(loc, 'in rewrite, find_mark failed on formula:\n\t' + str(formula))
        except MarkException as ex:
            new_subject = rewrite_aux(loc, ex.subject, equation)
            return replace_mark(formula, new_subject)
    else:
        error(loc, 'in rewrite, formula contains more than one mark:\n\t' + str(formula))

def rewrite_aux(loc, formula, equation):
  (lhs, rhs) = split_equation(loc, equation)
  if get_verbose():
    print('rewrite? ' + str(formula) + ' with equation ' + str(equation) \
          + '\n\t' + str(formula) + ' =? ' + str(lhs) + '\t' + str(formula == lhs))
  if formula == lhs:
    inc_rewrites()
    return rhs
  match formula:
    case TermInst(loc2, tyof, subject, tyargs, inferred):
      return TermInst(loc2, tyof, rewrite_aux(loc, subject, equation), tyargs, inferred)
    case Var(loc2, tyof, name, resolved_names):
      return formula
    case Bool(loc2, tyof, val):
      return formula
    case And(loc2, tyof, args):
      return And(loc2, tyof, [rewrite_aux(loc, arg, equation) for arg in args])
    case Or(loc2, tyof, args):
      return Or(loc2, tyof, [rewrite_aux(loc, arg, equation) for arg in args])
    case IfThen(loc2, tyof, prem, conc):
      return IfThen(loc2, tyof, rewrite_aux(loc, prem, equation),
                    rewrite_aux(loc, conc, equation))
    case All(loc2, tyof, var, pos, frm2):
      return All(loc2, tyof, var, pos, rewrite_aux(loc, frm2, equation))
    case Some(loc2, tyof, vars, frm2):
      return Some(loc2, tyof, vars, rewrite_aux(loc, frm2, equation))
    case Call(loc2, tyof, rator, args):
      call = Call(loc2, tyof,
                  rewrite_aux(loc, rator, equation),
                  [rewrite_aux(loc, arg, equation) for arg in args])
      if hasattr(formula, 'type_args'):
          call.type_args = formula.type_args
      return call
    case Switch(loc2, tyof, subject, cases):
      return Switch(loc2, tyof, rewrite_aux(loc, subject, equation),
                    [rewrite_aux(loc, c, equation) for c in cases])
    case SwitchCase(loc2, pat, body):
      return SwitchCase(loc2, pat, rewrite_aux(loc, body, equation))
    case RecFun(loc, name, typarams, params, returns, cases):
      return formula
    case Conditional(loc2, tyof, cond, thn, els):
      return Conditional(loc2, tyof, rewrite_aux(loc, cond, equation),
                         rewrite_aux(loc, thn, equation),
                         rewrite_aux(loc, els, equation))
    case Lambda(loc2, tyof, vars, body):
      return Lambda(loc2, tyof, vars, rewrite_aux(loc, body, equation))
  
    case Generic(loc2, tyof, typarams, body):
      return Generic(loc2, tyof, typarams, rewrite_aux(loc, body, equation))
  
    case TAnnote(loc2, tyof, subject, typ):
      return TAnnote(loc, tyof, rewrite_aux(loc, subject, equation), typ)

    case ArrayGet(loc2, tyof, arr, ind):
      return ArrayGet(loc, tyof, rewrite_aux(loc, arr, equation),
                      rewrite_aux(loc, ind, equation))
  
    case TLet(loc2, tyof, var, rhs, body):
      return TLet(loc2, tyof, var, rewrite_aux(loc, rhs, equation),
                  rewrite_aux(loc, body, equation))
  
    case Hole(loc2, tyof):
      return formula

    case Omitted(loc2, tyof):
      return formula
  
    case _:
      error(loc, 'in rewrite function, unhandled ' + str(formula))

def facts_to_str(env):
  result = ''
  for (x,p) in env.items():
    if isinstance(p, Formula) or isinstance(p, Term):
      result += x + ': ' + str(p) + '\n'
  return result

def isolate_difference_list(list1, list2):
  for (t1, t2) in zip(list1, list2):
    diff = isolate_difference(t1, t2)
    if diff:
      return diff
  return None
  
def isolate_difference(term1, term2):
  if get_verbose():
    print('isolate_difference(' + str(term1) + ',' + str(term2) + ')')
  if term1 == term2:
    return None
  else:
    match (term1, term2):
      case (Lambda(l1, tyof1, vs1, body1), Lambda(l2, tyof2, vs2, body2)):
        ren = {x: Var(l1, t2, y, []) for ((x,t1),(y,t2)) in zip(vs1, vs2)}
        return isolate_difference(body1.substitute(ren), body2)
      case (Call(l1, tyof1, fun1, args1), Call(l2, tyof2, fun2, args2)):
        if fun1 == fun2:
          return isolate_difference_list(args1, args2)
        else:
          return isolate_difference(fun1, fun2)
      case (SwitchCase(l1, p1, body1), SwitchCase(l2, p2, body2)):
        if p1 == p2:
          return isolate_difference(body1, body2)
        else:
          return (p1, p2)
      case (Switch(l1, tyof1, s1, cs1), Switch(l2, tyof2, s2, cs2)):
        if s1 == s2:
          return isolate_difference_list(cs1, cs2)
        else:
          return (s1, s2)
      case(And(l1, tyof1, args1), And(l2, tyof2, args2)):
        return isolate_difference_list(args1, args2)
      case (All(l1, tyof1, var1, _, body1), All(l2, tyof2, var2, _, body2)):
        return (term1, term2)
      case _:
        return (term1, term2)

def collect_all_if_then(loc, frm):
    """Returns a list of all variables that need be instantiated, and anythings that need applied"""
    match frm:
      case All(loc2, tyof, var, _, frm):
        (rest_vars, mps) = collect_all_if_then(loc, frm)
        x, t = var
        return ([Var(loc2, None, x, [])] + rest_vars, mps)
      case IfThen(loc2, tyof, prem, conc):
        return ([], [(prem, conc)])
      case And(loc2, tyof, args):
        mps1 = []
        for arg in args:
          try:
            (rest_vars, mps) = collect_all_if_then(loc, arg)
          except:
            continue
          # Making the executive decision that we can't apply for alls nested within ands
          if len(rest_vars) > 0: continue
          mps1 += mps
        if len(mps1) == 0:
          error(loc, "in 'apply', expected at least one if-then formula as a conjunct of " + str(frm))
        return ([], mps1)
      case _:
        error(loc, "in 'apply', expected an if-then formula, not " + str(frm))

def collect_all(frm):
    match frm:
      case All(loc2, tyof, var, _, frm):
        (rest_vars, body) = collect_all(frm)
        x, t = var
        return ([Var(loc2, None, x, [])] + rest_vars, body)
      case _:
        return ([], frm)
        
def check_proof(proof, env):
  if get_verbose():
    print('check_proof:')
    print('\t' + str(proof))
  ret = None
  match proof:
    case PRecall(loc, facts):
      results = []
      for fact in facts:
        new_fact = type_check_term(fact, BoolType(loc), env, None, [])
        if new_fact in env.proofs():
            results.append(new_fact)
        else:
            error(loc, 'Could not find a proof of\n\t' + str(new_fact) \
                  + '\nin the current scope\n' \
                  + 'Givens:\n' + env.proofs_str())
      if len(results) > 1:
          ret = And(loc, BoolType(loc), results)
      elif len(results) == 1:
          ret = results[0]
      else:
          error(loc, 'expected some facts after `recall`')

    case EvaluateFact(loc, subject):
      formula = check_proof(subject, env)
      set_reduce_all(True)
      red_formula = formula.reduce(env)
      set_reduce_all(False)
      ret = red_formula
          
    case ApplyDefsFact(loc, definitions, subject):
      defs = [type_synth_term(d, env, None, []) for d in definitions]
      defs = [d.reduce(env) for d in defs]
      formula = check_proof(subject, env)
      new_formula = apply_definitions(loc, formula, defs, env)
      ret = new_formula
      
    case EnableDefs(loc, definitions, body):
      defs = [type_synth_term(d, env, None, []) for d in definitions]
      defs = [d.reduce(env) for d in defs]
      old_defs = get_reduce_only()
      set_reduce_only(defs + old_defs)
      ret = check_proof(body, env)
      set_reduce_only(old_defs)
      
    case RewriteFact(loc, subject, equation_proofs):
      formula = check_proof(subject, env)
      eqns = [check_proof(proof, env) for proof in equation_proofs]
      new_formula = formula.reduce(env)
      for eq in eqns:
        if not is_equation(eq):
            error(loc, 'in rewrite, expected an equation, not:\n\t' + str(eq))
        reset_num_rewrites()
        new_formula = rewrite(loc, new_formula, eq)
        if get_num_rewrites() == 0:
            error(loc, 'no matches found for rewrite with\n\t' + str(eq) \
                  + '\nin\n\t' + str(new_formula))
        new_formula = new_formula.reduce(env)
      ret = new_formula
      
    case PHole(loc):
      incomplete_error(loc, 'unfinished proof')
      
    case PSorry(loc):
      error(loc, "can't use sorry in context with unkown goal")

    case PHelpUse(loc, proof):
      formula = check_proof(proof, env)
      error(loc, proof_use_advice(proof, formula, env))
      
    case PVar(loc, name):
      try:
        ret = env.get_formula_of_proof_var(proof)
        if ret:
            return ret
        else:
            error(loc, 'could not find given: ' + name)
      except Exception as e:
        error(loc, str(e))
      
    case PTrue(loc):
      ret = Bool(loc, BoolType(loc), True)
      
    case PTLetNew(loc, var, rhs, rest):
      new_rhs = type_synth_term(rhs, env, None, [])
      body_env = env.define_term_var(loc, var, new_rhs.typeof, new_rhs)
      ret = check_proof(rest, body_env)
      
    case PLet(loc, label, frm, reason, rest):
      new_frm = check_formula(frm, env)
      match new_frm:
        case Hole(loc2, tyof):
          proved_formula = check_proof(reason, env)
          error(loc, "\nhave " + label + ':\n\t' + str(proved_formula))
        case _:
          check_proof_of(reason, new_frm, env)
          body_env = env.declare_local_proof_var(loc, label, remove_mark(new_frm))
          ret = check_proof(rest, body_env)
      
    case PAnnot(loc, claim, reason):
      new_claim = check_formula(claim, env)
      match new_claim:
        case Hole(loc2, tyof):
          proved_formula = check_proof(reason, env)
          error(loc, '\nconclude ' + str(proved_formula))
        case _:
          check_proof_of(reason, new_claim, env)
          ret = remove_mark(new_claim)
      
    case PTerm(loc, term, because, rest):
      new_term = type_synth_term(term, env, None, [])
      frm = check_proof_of(because, new_term, env)
      ret = check_proof(rest, env)
      
    case PTuple(loc, pfs):
      frms = [check_proof(pf, env) for pf in pfs]
      ret = And(loc, BoolType(loc), frms)
      
    case PAndElim(loc, which, subject):
      formula = check_proof(subject, env)
      match formula:
        case And(loc2, tyof, args):
          if which >= len(args):
            error(loc, 'out of bounds, access to conjunct ' + str(which) \
                  + ' but there are only ' + str(len(args)) + ' conjuncts' \
                  + ' in formula\n\t' + str(formula))
          ret = args[which]
        case _:
          error(loc, 'expected a conjunction, not ' + str(formula))
          
    case ImpIntro(loc, label, prem, body):
      new_prem = check_formula(prem, env)
      body_env = env.declare_local_proof_var(loc, label, new_prem)
      conc = check_proof(body, body_env)
      ret = IfThen(loc, BoolType(loc), new_prem, conc)
      
    case AllIntro(loc, var, pos, body):
      body_env = env
      x, ty = var
      check_type(ty, env)
      if isinstance(ty, TypeType):
        body_env = body_env.declare_type(loc, x)
      else:
        body_env = body_env.declare_term_var(loc, x, ty)
      formula = check_proof(body, body_env)
      ret = All(loc, BoolType(loc), var, pos, formula)
      
    case AllElim(loc, univ, arg, pos):
      allfrm = check_proof(univ, env)
      match allfrm:
        case All(loc2, tyof, var, _, frm):
          sub = {}
          v, ty = var
          try:
            new_arg = type_check_term(arg, ty.substitute(sub), env, None, [])
            if isinstance(new_arg, TermInst):
                new_arg.inferred = False
          except Exception as e:
            if isinstance(ty, TypeType):
              error(loc, f"In instantiation of\n\t{str(univ)} : {str(allfrm)}\n" \
                    + f"expected a type argument, but was given '{arg}'")
            else:
              raise e
          if isinstance(ty, TypeType):
              error(loc, 'to instantiate:\n\t' + str(univ)+' : '+str(allfrm) \
                    +'\nwith type arguments, instead write:\n\t' \
                    +str(univ) + '<' + str(arg) + '>\n')
        case _:
          error(loc, 'expected all formula to instantiate, not ' + str(allfrm) \
                + '\nGivens:\n' + env.proofs_str())
      return instantiate(loc, allfrm, new_arg)

    case AllElimTypes(loc, univ, type_arg, _):
      allfrm = check_proof(univ, env)
      match allfrm:
        case All(loc2, tyof, vars, _, frm):
          sub = {}
          var, ty = vars
          check_type(type_arg, env)
          if not isinstance(ty, TypeType):
              error(loc, 'unexpected term parameter ' + str(var) + ' in type instantiation')
          sub[var] = type_arg
        case _:
          error(loc, 'expected all formula to instantiate, not ' + str(allfrm))
      return instantiate(loc, allfrm, type_arg)
  
    case ModusPonens(loc, imp, arg):
      ifthen = check_proof(imp, env)
      match ifthen:
        case IfThen(loc2, tyof, prem, conc):
          pass
        case All(loc2, tyof, var, _, body):
          pass
        case And(loc2, tyof, args):
          pass
        case _:
          ifthen = ifthen.reduce(env)
      match ifthen:
        case IfThen(loc2, tyof, prem, conc):
          check_proof_of(arg, prem, env)
          ret = conc
        case And(loc2, tyof, args):
          vars, imps = collect_all_if_then(loc, ifthen)
          arg_frm = check_proof(arg, env)
          rets = []
          for prem, conc in imps:
            try:
              check_proof_of(arg, prem, env)
              rets.append(conc)
            except Exception as e:
              pass
          if len(rets) == 1: ret = rets[0]
          elif len(rets) > 1: ret = And(loc2, tyof, rets)
          else:
            error(loc, "could not prove that " +str(arg_frm) +
                  " implies at least one of\n\t"\
                  + "\n\t".join([str(p) for p, _ in imps])
                  + "\nfor application of \n\t"+str(ifthen)
                  + "\nto \n\t" + str(arg))
        case All(loc2, tyof, _, _, body):
          (vars, imps) = collect_all_if_then(loc, ifthen)
          rets = []
          arg_frm = check_proof(arg, env)
          for prem, conc in imps: 
            try:
              matching = {}
              formula_match(loc, vars, prem, arg_frm, matching, env)
              for x in vars:
                if x.name not in matching.keys():
                  error(loc, "could not deduce an instantiation for variable "\
                        + str(x) + '\n' \
                        + 'for application of\n\t' + str(ifthen) + '\n'\
                        + 'to\n\t' + str(arg))
              rets.append(conc.substitute(matching))
            except Exception as e:
              msg = str(e) + '\nwhile trying to deduce instantiation of\n\t' + str(ifthen) + '\n'\
                  + 'to apply to\n\t' + str(arg_frm)
              # raise Exception(msg)
          if len(rets) == 1: ret = rets[0]
          elif len(rets) > 1: ret = And(loc2, tyof, rets)
          else:
            error(loc, "could not deduce an instantiation for any of the variables "\
                  + "for application of \n\t" + str(ifthen) + '\n'\
                  + 'to\n\t' + str(arg))
        case _:
          error(loc, "in 'apply', expected an if-then formula, not " + str(ifthen))
          
    case PInjective(loc, constr, eq_pf):
      check_type(constr, env)
      formula = check_proof(eq_pf, env)
      (a,b) = split_equation(loc, formula)
      match (a,b):
        case (Call(loc2, tyof2, Var(loc3,t1,f1,rs1), [arg1]),
              Call(loc4, tyof4, Var(loc5,t2,f2,rs2), [arg2])):
          if f1 != f2:
            error(loc, 'in injective, ' + str(f1) + ' ≠ ' + str(f2))
          if constr != f1:
            error(loc, 'in injective, ' + str(constr) + ' ≠ ' + str(f1))
          if not is_constructor(f1, env):
            error(loc, 'in injective, ' + str(f1) + ' not a constructor')
          return mkEqual(loc, arg1, arg2)
        case _:
          error(loc, 'in injective, non-applicable formula: ' + str(formula))
          
    case PSymmetric(loc, eq_pf):
      frm = check_proof(eq_pf, env)
      (a,b) = split_equation(loc, frm)
      return mkEqual(loc, b, a)

    case PTransitive(loc, eq_pf1, eq_pf2):
      eq1 = check_proof(eq_pf1, env)
      eq2 = check_proof(eq_pf2, env)
      (a,b1) = split_equation(loc, eq1)
      (b2,c) = split_equation(loc, eq2)
      b1r = b1.reduce(env)
      b2r = b2.reduce(env)
      if b1r != b2r:
        error(loc, 'error in transitive,\nyou proved\n\t'
              + str(eq1) + '\nand\n\t' + str(eq2) + '\n' \
              + 'but the middle formulas do not match:\n\t' \
              + str(b1r) + '\n≠\n\t' + str(b2r))
      else:
        return mkEqual(loc, a, c)
    case _:
      error(proof.location, 'need to be in goal-directed mode for\n\t' + str(proof))
  if get_verbose():
    print('\t=> ' + str(ret))
  return ret

def get_type_name(ty):
  match ty:
    case Var(l1, tyof, n, rs):
      return ty
    case TypeInst(l1, ty, type_args):
      return get_type_name(ty)
    case _:
      raise Exception('unhandled case in get_type_name: ' + repr(ty))

def get_type_args(ty):
  match ty:
    case Var(l1, tyof, n, rs):
      return []
    case TypeInst(l1, ty, type_args):
      return type_args
    case _:
      raise Exception('unhandled case in get_type_args')

label_count = 0

def reset_label():
    label_count = 1

def generate_label():
    global label_count
    l = 'label_' + str(label_count)
    label_count = label_count + 1
    return l
  
def proof_use_advice(proof, formula, env):
    prefix = 'Advice about using fact:\n' \
        + '\t' + str(formula) + '\n\n'
    match formula:
      case Bool(loc, tyof, True):
        return prefix + '\tThe "true" fact is useless.\n'
      case Bool(loc, tyof, False):
        return prefix \
            + '\tUse this "false" fact to implicitly prove anything!\n'
      case And(loc, tyof, args):
        return prefix \
            + '\tUse this logical-and to implicitly prove any of its parts:\n' \
            + '\n'.join('\t\t' + str(arg) for arg in args)
      case Or(loc, tyof, args):
        reset_label()
        return prefix \
            + '\tUse this logical-or by proceeding with a "cases" statement:\n'\
            + '\t\tcases ' + str(proof) + '\n' \
            + '\n'.join(['\t\tcase ' + generate_label() + ' : ' + str(arg) \
                         + ' { ? }' for arg in args])
      case IfThen(loc, tyof, prem, conc):
        return prefix \
            + '\tApply this if-then formula to a proof of its premise:\n' \
            + '\t\t' + str(prem) + '\n' \
            + '\tto obtain a proof of its conclusion:\n' \
            + '\t\t' + str(conc) + '\n' \
            + '\tby using an apply-to statement:\n' \
            + '\t\tapply ' + str(proof) + ' to ?'
      case All(loc, tyof, var, (s, e), body):
        vars = [var]
        while s != 0:
          match body:
            case All(loc2, tyof2, var2, (s, e2), body):
              vars.append(var2)

        letters = []
        new_vars = {}
        i = 65
        type_param = False
        for (x,ty) in vars:
          if isinstance(ty, TypeType):
              type_param = True
          letters.append(chr(i))
          new_vars[x] = Var(loc,ty, chr(i), [])
          i = i + 1
        plural = 's' if len(vars) > 1 else ''
        pronoun = 'them' if len(vars) > 1 else 'it'
        
        if type_param:
            how = ' between `<` and `>` like so:\n' \
                + '\t\t ' + str(proof) + '<' + ', '.join(letters) + '>' + '\n'
        else:
            how = ' in square-brackets like so:\n' \
                + '\t\t ' + str(proof) + '[' + ', '.join(letters) + ']' + '\n'
        
        return prefix \
            + '\tInstantiate this all formula with your choice' + plural \
            + ' for ' + ', '.join([base_name(x) for (x,ty) in vars]) + '\n' \
            + '\tby writing ' + pronoun + how \
            + '\tto obtain a proof of:\n' \
            + '\t\t' + str(body.substitute(new_vars))
      case Some(loc, tyof, vars, body):
        letters = []
        new_vars = {}
        i = 65
        for (x,ty) in vars:
            letters.append(chr(i))
            new_vars[x] = Var(loc,ty, chr(i), [])
            i = i + 1
        new_body = body.substitute(new_vars)
        return prefix \
            + 'To use this "some" formula, proceed with:\n' \
            + '\tobtain ' + ', '.join(letters) + \
            ' where label: ' + str(new_body) + ' from ' + str(proof) +'\n' \
            + 'where ' + ', '.join(letters) \
            + (' are new names of your choice' if len(vars) > 1 \
               else ' is a new name of your choice' ) + ',\n' \
            + 'followed by a proof of the goal.'

      case Call(loc2, tyof2, Var(loc3, tyof3, '=', rs), [lhs, rhs]):
        return prefix \
            + '\tYou can use this equality in a rewrite statement:\n' \
            + '\t\trewrite ' + str(proof) + '\n'
      case _:
        return 'Sorry, I have no advice for this kind of formula.'

def make_unique(name, env):
    if name in env:
        return make_unique(name + "'", env)
    else:
        return name

def is_recursive(name, typ):
    match typ:
      case Var(l1, tyof, n, rs):
        return name == n
      case TypeInst(l1, ty, type_args):
        return is_recursive(name, ty)
      case _:
        return False

def update_all_head(r):
    match r:
      case All(loc2, tyof, var, (s, e), frm):
        if s == 0:
          return All(loc2, tyof, var, (s, e-1), frm)
        else:
          return All(loc2, tyof, var, (s, e-1), update_all_head(frm))
      case _: # THIS SHOULD NEVER HAPPEN
        error(loc2, "update_all_head internal error")
    
def proof_advice(formula, env):
    prefix = 'Advice:\n'
    match formula:
      case Bool(loc, tyof, True):
        return prefix + '\tYou can prove "true" with a period.\n'
      case Bool(loc, tyof, False):
        return prefix \
            + '\tProve "false" by proving a contradiction:\n' \
            + '\tif you prove both "P" and "not P", \n' \
            + '\tthen "apply (recall not P) to (recall P)" proves "false".\n'
      case And(loc, tyof, args):
        return prefix \
            + '\tProve this logical-and formula by proving each of its'\
            + ' parts,\n\tshown below, then combine the proofs with commas.\n' \
            + '\n'.join('\t\t' + str(arg) for arg in args)
      case Or(loc, tyof, args):
        return prefix \
            + '\tProve this logical-or formula by proving one of its parts:\n' \
            + '\n'.join('\t\t' + str(arg) for arg in args)
      case IfThen(loc, tyof, prem, conc):
        return prefix \
            + '\tProve this if-then formula with:\n' \
            + '\t\tassume label: ' + str(prem) + '\n' \
            + '\tfollowed by a proof of:\n' \
            + '\t\t' + str(conc)
      case All(loc, tyof, var, (s, e), body):
        x, ty = var
        
        if s != 0:
          body = update_all_head(body)
        arb_advice = prefix \
            + '\tProve this "all" formula with:\n' \
            + '\t\tarbitrary ' + base_name(x) + ':' + str(ty) + '\n' \
            + '\tfollowed by a proof of:\n' \
            + '\t\t' + str(body)

        # NOTE: Maybe we shouldn't give induction advice for non recursively
        # defined unions. However right now we will because I haven't added
        # that check yet. Maybe even suggest a switch instead.
        
        var_x, var_ty = var
        match var_ty:
          # NOTE: These are the types that are handled in get_type_name, and
          # get_def_of_type_var
          case TypeInst() | Var():
            pass
          case _:
            return arb_advice # don't give induction adivce for type variables

        # When foralls are generated, the def of type var is not in the environment?
        # Seems to be a problem with extensionality
        # I'm ok for now with just failing the match if this happens
        ty = None
        try:
          ty = env.get_def_of_type_var(get_type_name(var_ty))
        except:
          pass

        match ty:
          case Union(loc2, name, typarams, alts):
            if len(alts) < 2:
              return arb_advice # Can't do induction if there's only one case
                
            ind_advice = '\n\n\tAlternatively, you can try induction with:\n' \
              +  '\t\tinduction ' + str(var_ty) + '\n'
                
            for alt in alts:
                match alt:
                  case Constructor(loc3, constr_name, param_types):
                    params = [make_unique(type_first_letter(ty)+str(i+1), env)\
                              for i,ty in enumerate(param_types)]
                    ind_advice += '\t\tcase ' + base_name(constr_name)
                    if len(param_types) > 0:
                      ind_advice += '(' + ', '.join(params) + ')'
                    num_recursive = sum([1 if is_recursive(name, ty) else 0 \
                                         for ty in param_types])
                    if num_recursive > 0:
                      rec_params =[(p,ty) for (p,ty) in zip(params,param_types)\
                                   if is_recursive(name, ty)]
                      ind_advice += ' suppose '
                      ind_advice += ',\n\t\t\t'.join(['IH' + str(i+1) + ': ' \
                            + str(body.substitute({var_x: Var(loc3, param_ty, param, [])})) \
                            for i, (param,param_ty) in enumerate(rec_params)])

                    ind_advice += ' {\n\t\t  ?\n\t\t}\n'
                    
            return arb_advice + ind_advice
        
          case _:
            return arb_advice


      case Some(loc, tyof, vars, body):
        letters = []
        new_vars = {}
        i = 65
        for (x,ty) in vars:
            letters.append(chr(i))
            new_vars[x] = Var(loc,ty, chr(i), [])
            i = i + 1
        return prefix \
            + '\tProve this "some" formula with:\n' \
            + '\t\tchoose ' + ', '.join(letters) + '\n' \
            + '\twhere you replace ' + ', '.join(letters) \
            + ' with your choice(s),\n' \
            + '\tthen prove:\n' \
            + '\t\t' + str(body.substitute(new_vars))
      case Call(loc2, tyof2, Var(loc3, tyof3, '=', rs), [lhs, rhs]):
        return prefix \
            + '\tTo prove this equality, one of these statements might help:\n'\
            + '\t\tdefinition\n' \
            + '\t\trewrite\n' \
            + '\t\tequations\n'
      case TLet(loc2, _, var, rhs, body):
        return proof_advice(body, env)
      case _:
        for (name, b) in env.dict.items():
            if isinstance(b, ProofBinding) and b.local and b.formula == formula:
                msg = '\nYou can conclude the proof with:\n'
                if base_name(name) == '_':
                    msg += '\trecall ' + str(formula)
                else:
                    msg += '\tconclude ' + str(formula) \
                        + ' by ' + base_name(name)                
                return msg

        return '\n'
  
def check_proof_of(proof, formula, env):
  if get_verbose():
    print('check_proof_of: ' + str(formula) + '?')
    print('\t' + str(proof))
  match proof:
    case PHole(loc):
      new_formula = check_formula(remove_mark(formula), env)
      env_str = env.proofs_str()
      if len(env_str) > 0:
          givens = '\nGivens:\n' + env_str
      else:
          givens = ''
      incomplete_error(loc, 'incomplete proof\n' \
                       + 'Goal:\n\t' + str(new_formula) + '\n'\
                       + proof_advice(new_formula, env) + givens)

    case PSorry(loc):
      warning(loc, 'unfinished proof')
      
    case EnableDefs(loc, definitions, subject):
      defs = [type_synth_term(d, env, None, []) for d in definitions]
      defs = [d.reduce(env) for d in defs]
      old_defs = get_reduce_only()
      set_reduce_only(defs + old_defs)
      check_proof_of(subject, formula, env)
      set_reduce_only(old_defs)
      
    case PReflexive(loc):
      match formula:
        case Call(loc2, tyof2, Var(loc3, tyof3, '=', rs), [lhs, rhs]):
          lhsNF = lhs.reduce(env)
          rhsNF = rhs.reduce(env)
          if lhsNF != rhsNF:
            (small_lhs, small_rhs) = isolate_difference(lhsNF, rhsNF)
            msg = 'error in proof by reflexive:\n'
            if small_lhs == lhsNF:
              msg = msg + str(lhsNF) + ' ≠ ' + str(rhsNF)
            else:
              msg = msg + str(small_lhs) + ' ≠ ' + str(small_rhs) + '\n' \
                + 'therefore\n' + str(lhsNF) + ' ≠ ' + str(rhsNF)
            error(proof.location, msg + '\n\nGivens:\n\t' + env.proofs_str())
        case _:
          error(proof.location, 'reflexive proves an equality, not ' \
                + str(formula))
          
    case PSymmetric(loc, eq_pf):
      (a,b) = split_equation(loc, formula)
      flip_formula = mkEqual(loc, b, a)
      check_proof_of(eq_pf, flip_formula, env)

    case PTransitive(loc, eq_pf1, eq_pf2):
      (a1,c) = split_equation(loc, formula)
      
      eq1 = check_proof(eq_pf1, env)
      (a2,b) = split_equation(loc, eq1)
      
      check_proof_of(eq_pf2, mkEqual(loc, b, c), env)
      
      a1r = a1.reduce(env)
      a2r = a2.reduce(env)
      if remove_mark(a1r) != remove_mark(a2r):
        error(loc, 'for transitive,\n\t' + str(a1r) + '\n≠\n\t' + str(a2r))

    case PInjective(loc, constr, eq_pf):
      check_type(constr, env)
      if not is_constructor(constr.name, env):
        error(loc, 'in injective, ' + constr.name + ' not a constructor')
      (a,b) = split_equation(loc, formula)
      lhs = Call(loc, None, constr, [a])
      rhs = Call(loc, None, constr, [b])
      flip_formula = mkEqual(loc, lhs, rhs)
      check_proof_of(eq_pf, flip_formula, env)

    case PExtensionality(loc, proof):
      (lhs,rhs) = split_equation(loc, formula)
      match lhs.typeof:
        case FunctionType(loc2, [], typs, ret_ty):
          names = [generate_name('x') for ty in typs]
          args = [Var(loc, None, x, []) for x in names]
          call_lhs = Call(loc, None, lhs, args)
          call_rhs = Call(loc, None, rhs, args)
          formula = mkEqual(loc, call_lhs, call_rhs)
          for i, v in enumerate(reversed(list(zip(names, typs)))):
            formula = All(loc, None, v, (i, len(names)), formula)
          check_proof_of(proof, formula, env)
        case FunctionType(loc2, ty_params, params, ret_ty):
          error(loc, 'extensionality expects function without any type parameters, not ' + str(len(ty_params)))
        case _:
          error(loc, 'extensionality expects a function, not ' + str(lhs.typeof))
      
    case AllIntro(loc, var, _, body):
      x, ty = var
      check_type(ty, env)
      match formula:
        case All(loc2, tyof, var2, (s, e), formula2):
          sub = {}
          sub[ var2[0] ] = Var(loc, var[1], var[0], [ var[0] ])
          
          frm2 = formula2.substitute(sub)

          if s != 0: 
            frm2 = update_all_head(frm2)

          body_env = env.declare_term_vars(loc, [var])
          check_proof_of(body, frm2, body_env)
        case _:
          error(loc, 'arbitrary is proof of an all formula, not\n' \
                + str(formula))
                
    case SomeIntro(loc, witnesses, body):
      # room for improvement, if var has type annotation, could type_check the witness
      witnesses = [type_synth_term(trm, env, None, []) for trm in witnesses]
      match formula:
        case Some(loc2, tyof, vars, formula2):
          sub = {var[0]: trm for (var,trm) in zip(vars, witnesses) }
          body_frm = formula2.substitute(sub)
          check_proof_of(body, body_frm, env)
        case _:
          error(loc, "choose expects the goal to start with 'some', not " + str(formula))
          
    case SomeElim(loc, witnesses, label, prop, some, body):
      someFormula = check_proof(some, env)
      match someFormula:
        case Some(loc2, tyof, vars, formula2):
          sub = {var[0]: Var(loc2, None, x, [x]) for (var,x) in zip(vars,witnesses)}
          witnessFormula = formula2.substitute(sub)
          
          witnesses_types = [(x,var[1]) for (var,x) in zip(vars,witnesses)]
          body_env = env.declare_term_vars(loc, witnesses_types)
          if prop:
            prop = check_formula(prop, body_env)
            check_implies(loc, witnessFormula.reduce(env), prop.reduce(body_env))
          else:
            prop = witnessFormula
          body_env = body_env.declare_local_proof_var(loc, label, prop)
          check_proof_of(body, formula, body_env)
        case _:
          error(loc, "obtain expects 'from' to be a proof of a 'some' formula, not " + str(someFormula))
        
    case ImpIntro(loc, label, None, body):
      match formula:
        case IfThen(loc2, tyof, prem, conc):
          body_env = env.declare_local_proof_var(loc, label, prem)
          check_proof_of(body, conc, body_env)
        case _:
          error(proof.location, 'expected proof of ' + str(formula) + \
                '\n\tnot a proof of if-then: ' + str(proof))
          
    case ImpIntro(loc, label, prem1, body):
      new_prem1 = check_formula(prem1, env)
      match formula:
        case IfThen(loc2, tyof, prem2, conc):
          prem1_red = new_prem1.reduce(env)
          prem2_red = prem2.reduce(env)
          if prem1_red != prem2_red:
            (small1, small2) = isolate_difference(prem1_red, prem2_red)
            msg = str(prem1_red) + ' ≠ ' + str(prem2_red) + '\n' \
                + 'because\n' + str(small1) + ' ≠ ' + str(small2)
            error(loc, 'mismatch in premise:\n' + msg)
          body_env = env.declare_local_proof_var(loc, label, new_prem1)
          check_proof_of(body, conc, body_env)
        case _:
          error(proof.location, 'the assume statement is for if-then formula, not ' + str(formula))

    # define x = t
    case PTLetNew(loc, var, rhs, rest):
      new_rhs = type_synth_term(rhs, env, None, [])
      body_env = env.define_term_var(loc, var, new_rhs.typeof, new_rhs)
      equation = mkEqual(loc, new_rhs, Var(loc, None, var, [])).reduce(env)
      frm = rewrite(loc, formula.reduce(env), equation)
      new_body_env = Env({k: ProofBinding(b.location, \
                                          rewrite(loc, b.formula, equation), \
                                          b.local) \
                          if isinstance(b, ProofBinding) else b \
                           for (k,b) in body_env.dict.items()})
      ret = check_proof_of(rest, frm, new_body_env)

    # have X: P by frm
    case PLet(loc, label, frm, reason, rest):
      new_frm = check_formula(frm, env)
      match new_frm:
        case Hole(loc2, tyof):
          proved_formula = check_proof(reason, env)
          warning(loc, "\nhave " + base_name(label) + ':\n\t' + str(proved_formula))
          body_env = env.declare_local_proof_var(loc, label, proved_formula)
        case _:
          check_proof_of(reason, new_frm, env)
          body_env = env.declare_local_proof_var(loc, label, remove_mark(new_frm))
      check_proof_of(rest, formula, body_env)

    case PAnnot(loc, claim, reason):
      new_claim = check_formula(claim, env)
      match new_claim:
        case Hole(loc2, tyof):
          check_proof_of(reason, formula, env)
          error(loc, '\nconclude ' + str(formula))
        case _:
          claim_red = new_claim.reduce(env)
          formula_red = formula.reduce(env)
          check_implies(loc, claim_red, remove_mark(formula_red))
          check_proof_of(reason, claim_red, env)

    case EvaluateGoal(loc):
      set_reduce_all(True)
      red_formula = formula.reduce(env)
      set_reduce_all(False)
      if red_formula != Bool(loc, None, True):
          error(loc, 'the goal did not evaluate to `true`, but instead:\n\t' + str(red_formula))
      return red_formula
  
    case ApplyDefs(loc, definitions):
      defs = [type_synth_term(d, env, None, []) for d in definitions]
      defs = [d.reduce(env) for d in defs]
      new_formula = apply_definitions(loc, formula, defs, env)
      if new_formula != Bool(loc, None, True):
          error(loc, 'remains to prove:\n\t' + str(new_formula))

    case Rewrite(loc, equation_proofs):
      equations = [check_proof(proof, env) for proof in equation_proofs]
      eqns = [equation.reduce(env) for equation in equations]
      new_formula = formula.reduce(env)
      new_formula = apply_rewrites(loc, new_formula, eqns, env)
      if new_formula != Bool(loc, None, True):
          error(loc, 'remains to prove:\n\t' + str(new_formula))
    
    case Suffices(loc, claim, reason, rest):
      def_or_rewrite = False
      
      match reason:
        case ApplyDefs(loc2, defs):
           def_or_rewrite = True
           definitions = [type_synth_term(d, env, None, []) for d in defs]
           equation_proofs = [] 
        case ApplyDefsGoal(loc2, defs, Rewrite(loc3, eqns)):
           def_or_rewrite = True
           definitions = [type_synth_term(d, env, None, []) for d in defs]
           equation_proofs = eqns 
        case Rewrite(loc2, eqns):
           def_or_rewrite = True
           definitions = []
           equation_proofs = eqns 
        case _:
           def_or_rewrite = False

      if def_or_rewrite:
        new_claim = type_check_term(claim, BoolType(loc), env, None, [])
        defs = [d.reduce(env) for d in definitions]
        equations = [check_proof(proof, env) for proof in equation_proofs]
        red_claim = new_claim.reduce(env)

        new_formula = apply_definitions(loc, formula, defs, env)
        new_formula = new_formula.reduce(env)

        eqns = [equation.reduce(env) for equation in equations]
        for eq in eqns:
          if not is_equation(eq):
            error(loc, 'in rewrite, expected an equation, not:\n\t' + str(eq))
          new_formula = rewrite(loc, new_formula, eq)
          new_formula = new_formula.reduce(env)

        match red_claim:
          case Omitted(loc2, tyof):
            check_proof_of(rest, new_formula, env)
          case Hole(loc2, tyof):
            try:
              newer_formula = check_formula(new_formula, env)
            except Exception as e:
              error(loc2, 'blah: ' + str(new_formula) + '\n' + str(e))
            warning(loc, '\nsuffices to prove:\n\t' + str(newer_formula))
            check_proof_of(rest, newer_formula, env)
          case _:
            try:
              check_implies(loc, red_claim, new_formula)
            except Exception as e:
              error(loc, str(e) + '\nGivens:\n' + env.proofs_str())
            check_proof_of(rest, red_claim, env)
      else:
        new_claim = type_check_term(claim, BoolType(loc), env, None, [])
        claim_red = new_claim.reduce(env)
        imp = IfThen(loc, BoolType(loc), claim_red, formula).reduce(env)
        check_proof_of(reason, imp, env)
        check_proof_of(rest, claim_red, env)

    case PTuple(loc, pfs):
      try:
        match formula:
          case And(loc2, tyof2, frms):
            if len(frms) == len(pfs):
              for (frm,pf) in zip(frms, pfs):
                check_proof_of(pf, frm, env)
            else:
              error(loc, 'expected ' + str(len(frms)) + ' proofs but only got '\
                    + str(len(pfs)))
          case _:
            error(loc, 'comma proves logical-and, not ' + str(formula))
      except IncompleteProof as ex:
        raise ex
      except Exception as ex1:
        try:
          form = check_proof(proof, env)
          form_red = form.reduce(env)
          formula_red = formula.reduce(env)
          check_implies(proof.location, form_red, remove_mark(formula_red))
        except Exception as ex2:
          error(loc, 'failed to prove: ' + str(formula) + '\n' \
                + '\tfirst tried each subproof in goal-directed mode, but:\n' \
                + str(ex1) + '\n' \
                + '\tthen tried synthesis mode, but:\n'\
                + str(ex2))
            
    case Cases(loc, subject, cases):
      sub_frm = check_proof(subject, env)
      match sub_frm:
        case Or(loc1, tyof, frms):
          for (frm, (label,frm2,case)) in zip(frms, cases):
            if frm2:
                new_frm2 = check_formula(frm2, env)
            if frm2 and (frm != new_frm2): # was frm != red_frm2
              error(loc, 'case ' + str(new_frm2) + '\ndoes not match alternative in goal: \n' + str(frm))
            body_env = env.declare_local_proof_var(loc, label, frm)
            check_proof_of(case, formula, body_env)
        case _:
          error(proof.location, "expected 'or', not " + str(sub_frm))
          
    case Induction(loc, typ, cases):
      check_type(typ, env)
      match formula:
        case All(loc2, tyof, (var,ty), _, frm):
          if typ != ty:
            error(loc, "type of induction: " + str(typ) \
                  + "\ndoes not match the all-formula's type: " + str(ty))
        case _:
          error(loc, 'induction expected an all-formula, not ' + str(formula))
      match env.get_def_of_type_var(get_type_name(typ)):
        case Union(loc2, name, typarams, alts):
          if len(cases) != len(alts):
            error(loc, 'expected ' + str(len(alts)) + ' cases for induction' \
                  + ', but only have ' + str(len(cases)))
          cases_present = {}
          for (constr,indcase) in zip(alts, cases):
            check_pattern(indcase.pattern, typ, env, cases_present)
            if get_verbose():
                print('\nCase ' + str(indcase.pattern))
            if indcase.pattern.constructor.name != constr.name:
              error(indcase.location, "expected a case for " + str(base_name(constr.name)) \
                    + " not " + str(base_name(indcase.pattern.constructor.name)))
            if len(indcase.pattern.parameters) != len(constr.parameters):
              error(indcase.location, "expected " + str(len(constr.parameters)) \
                    + " arguments to " + base_name(constr.name) \
                    + " not " + str(len(indcase.pattern.parameters)))
            induction_hypotheses = [instantiate(loc, formula,
                                                Var(loc,None,param,[])).reduce(env)
                                    for (param, ty) in 
                                    zip(indcase.pattern.parameters,
                                        constr.parameters)
                                    if is_recursive(name, ty)]
            body_env = env
              
            if len(typarams) > 0:
              sub = { T: ty for (T,ty) in zip(typarams, typ.arg_types)}
              parameter_types = [p.substitute(sub) for p in constr.parameters]
            else:
              parameter_types = constr.parameters
            body_env = body_env.declare_term_vars(loc, zip(indcase.pattern.parameters,
                                                           parameter_types))
            
            trm = pattern_to_term(indcase.pattern)
            new_trm = type_check_term(trm, typ, body_env, None, [])
            if isinstance(new_trm, TermInst):
                new_trm.inferred = False
            pre_goal = instantiate(loc, formula, new_trm)
            goal = check_formula(pre_goal, body_env)
            
            for ((x,frm1),frm2) in zip(indcase.induction_hypotheses, induction_hypotheses):
              if frm1 != None:
                new_frm1 = check_formula(frm1, body_env)
                if new_frm1 != frm2:
                  (small_frm1,small_frm2) = isolate_difference(new_frm1, frm2)
                  msg = 'incorrect induction hypothesis, expected\n' \
                      + str(frm2) + '\nbut got\n' + str(new_frm1) \
                      + '\nin particular\n' + str(small_frm1) + '\n≠\n' + str(small_frm2) 
                  error(loc, msg)
              body_env = body_env.declare_local_proof_var(loc, x, frm2)
            
            check_proof_of(indcase.body, goal, body_env)
        case blah:
          error(loc, "induction expected name of union, not " + str(typ)
                + '\nwhich resolves to\n' + str(blah) + '\nin ' + str(env))

    case SwitchProof(loc, subject, cases):
      new_subject = type_synth_term(subject, env, None, [])
      ty = new_subject.typeof
      match ty:
        case BoolType(loc2):
          # check exhaustiveness
          has_true_case = False
          has_false_case = False
          for scase in cases:
            match scase.pattern:
              case PatternBool(l1, True):
                has_true_case = True
              case PatternBool(l1, False):
                has_false_case = True
              case _:
                raise Exception('unhandled case in switch proof')
          if not has_true_case:
            error(loc, 'missing case for true')
          if not has_false_case:
            error(loc, 'missing case for false')
            
          # check each case
          for scase in cases:
            if not isinstance(scase.pattern, PatternBool):
              error(scase.location, "expected pattern 'true' or 'false' in switch on bool")
            subject_case = Bool(scase.location, BoolType(scase.location), True) if scase.pattern.value \
                           else Bool(scase.location, BoolType(scase.location), False)
            equation = mkEqual(scase.location, new_subject, subject_case)

            body_env = env
            assumptions = [(label, check_formula(asm, body_env) if asm else None) for (label,asm) in scase.assumptions]
            if len(assumptions) == 1:
              if assumptions[0][1] != None and assumptions[0][1] != equation:
                (small_case_asm, small_eqn) = isolate_difference(assumptions[0][1], equation)
                msg = 'expected assumption\n' + str(equation) \
                    + '\nnot\n' + str(assumptions[0][1]) \
                    + '\nbecause\n\t' + str(small_case_asm) + ' ≠ ' + str(small_eqn)
                error(scase.location, msg)
              body_env = body_env.declare_local_proof_var(loc, assumptions[0][0], equation)

            if len(assumptions) > 1:
              error(scase.location, 'only one assumption is allowed in a switch case')
            frm = rewrite(loc, formula.reduce(env), equation.reduce(env))
            new_frm = frm.reduce(env)
            check_proof_of(scase.body, new_frm, body_env)
        case TypeType(_):
          # As far as I know, it is not possible to switch on a type
          error(loc, "In 'switch' expected a variable, got " + str(new_subject))
        case _:
          tname = get_type_name(ty)
          match env.get_def_of_type_var(tname):
            case Union(loc2, name, typarams, alts):
              if len(cases) != len(alts):
                error(loc, 'expected ' + str(len(alts)) + ' cases in switch, but only have ' + str(len(cases)))
              cases_present = {}
              for (constr,scase) in zip(alts, cases):
                check_pattern(scase.pattern, ty, env, cases_present)
                if scase.pattern.constructor.name != constr.name:
                  error(scase.location, "expected a case for " + str(constr) \
                        + " not " + str(scase.pattern.constructor))
                if len(scase.pattern.parameters) != len(constr.parameters):
                  error(scase.location, "expected " + str(len(constr.parameters)) \
                        + " arguments to " + base_name(constr.name) \
                        + " not " + str(len(scase.pattern.parameters)))
                subject_case = pattern_to_term(scase.pattern)
                body_env = env

                tyargs = get_type_args(ty)
                sub = {T:ty for (T,ty) in zip(typarams, tyargs)}
                constr_params = [ty.substitute(sub) for ty in constr.parameters]
                body_env = body_env.declare_term_vars(loc, zip(scase.pattern.parameters,
                                                               constr_params))
                
                new_subject_case = type_check_term(subject_case, ty, body_env, None, [])
                if isinstance(new_subject_case, TermInst):
                    new_subject_case.inferred = False

                assumptions = [(label,check_formula(asm, body_env) if asm else None) for (label,asm) in scase.assumptions]
                if len(assumptions) == 1:
                  assumption = mkEqual(scase.location, new_subject, subject_case)
                  new_assumption = type_synth_term(assumption, body_env, None, [])
                  if assumptions[0][1] != None:
                      case_assumption = type_synth_term(assumptions[0][1], body_env, None, [])
                      if case_assumption != new_assumption:
                          error(scase.location, 'in case, expected suppose of\n' + str(new_assumption) \
                                + '\nnot\n' + str(case_assumption))
                  body_env = body_env.declare_local_proof_var(loc, assumptions[0][0], new_assumption)
                if len(assumptions) > 1:
                  error(scase.location, 'only one assumption is allowed in a switch case')
                  
                if isinstance(new_subject, Var):
                  frm = formula.substitute({new_subject.name: new_subject_case})
                else:
                  frm = formula
                red_frm = frm.reduce(body_env)
                check_proof_of(scase.body, red_frm, body_env)
            case _:
              error(loc, "switch expected union type or bool, not " + str(ty))
          
    case RewriteGoal(loc, equation_proofs, body):
      equations = [check_proof(proof, env) for proof in equation_proofs]
      eqns = [equation.reduce(env) for equation in equations]
      new_formula = formula.reduce(env)
      for eq in eqns:
        if not is_equation(eq):
          error(loc, 'in rewrite, expected an equation, not:\n\t' + str(eq))
        reset_num_rewrites()
        new_formula = rewrite(loc, new_formula, eq)
        if get_num_rewrites() == 0:
            error(loc, 'no matches found for rewrite with\n\t' + str(eq) \
                  + '\nin\n\t' + str(new_formula))
        new_formula = new_formula.reduce(env)
      check_proof_of(body, new_formula.reduce(env), env)
      #warning(loc, 'old-style rewrite will be deprecated')
    case ApplyDefsGoal(loc, definitions, body):
      defs = [type_synth_term(d, env, None, []) for d in definitions]
      defs = [d.reduce(env) for d in defs]
      new_formula = apply_definitions(loc, formula, defs, env)
      check_proof_of(body, new_formula, env)
      #warning(loc, 'old-style definition will be deprecated')
    case _:
      form = check_proof(proof, env)
      form_red = form.reduce(env)
      formula_red = formula.reduce(env)
      check_implies(proof.location, form_red, remove_mark(formula_red))

def apply_definitions(loc, formula, defs, env):
  num_marks = count_marks(formula)
  if num_marks == 0:
      new_formula = formula
  elif num_marks == 1:
      try:
          find_mark(formula)
          error(loc, 'in apply_definitions, find_mark failed on formula:\n\t' \
                + str(formula))
      except MarkException as ex:
          new_formula = ex.subject
  else:
      error(loc, 'in definition, formula contains more than one mark:\n\t' \
            + str(formula))

  for var in defs:
    if isinstance(var, Var): # it's a bit strange that RecDef's can find there way into defs -Jeremy
      reduced_one = False
      for var_name in var.resolved_names:
          rvar = Var(var.location, var.typeof, var_name, [var_name])
          rhs = env.get_value_of_term_var(rvar)
          if rhs == None:
              error(loc, 'could not find definition of ' + str(rvar))
          else:
              reset_reduced_defs()
              if get_verbose():
                  print('definition subst ' + rvar.name + ' => ' + str(rhs))
              new_formula = new_formula.substitute({rvar.name: rhs})
              new_formula = new_formula.reduce(env)
              if rvar.name in get_reduced_defs():
                  reduced_one = True
      if not reduced_one:
          error(loc, 'could not find a place to apply definition of ' \
                + base_name(var.name) \
                + ' in:\n' + '\t' + str(new_formula))

  if num_marks == 0:          
      return new_formula
  else:
      return replace_mark(formula, new_formula).reduce(env)

def apply_rewrites(loc, formula, eqns, env):
  num_marks = count_marks(formula)
  if num_marks == 0:
      new_formula = formula
  elif num_marks == 1:
      try:
          find_mark(formula)
          error(loc, 'in apply_rewrites, find_mark failed on formula:\n\t' + str(formula))
      except MarkException as ex:
          new_formula = ex.subject
  else:
      error(loc, 'in rewrite, formula contains more than one mark:\n\t' + str(formula))

  for eq in eqns:
    if not is_equation(eq):
        error(loc, 'in rewrite, expected an equation, not:\n\t' + str(eq))
    reset_num_rewrites()
    new_formula = rewrite_aux(loc, new_formula, eq)
    if get_num_rewrites() == 0:
        error(loc, 'no matches found for rewrite with\n\t' + str(eq) \
              + '\nin\n\t' + str(new_formula))
    new_formula = new_formula.reduce(env)
      
  if num_marks == 0:          
      return new_formula
  else:
      return replace_mark(formula, new_formula).reduce(env)

  
def formula_match(loc, vars, goal_frm, frm, matching, env):
  if get_verbose():
    print("formula_match(" + str(goal_frm) + "," + str(frm) + ")")
    print("\tin  " + ','.join([str(x) for x in vars]))
    print("\twith " + ','.join([x + ' := ' + str(f) for (x,f) in matching.items()]))
  match (goal_frm, frm):
    case (Var(l1, t1, n1, rs1), Var(l2, t2, n2, rs2)) if n1 == n2:
      pass
    case (Var(l1, t1, name, rs1), _) if goal_frm in vars:
      if name in matching.keys():
        formula_match(loc, vars, matching[name], frm, matching, env)
      else:
        if get_verbose():
            print("formula_match, " + base_name(name) + ' := ' + str(frm))
        matching[name] = frm
    case (Call(loc2, tyof2, goal_rator, goal_rands),
          Call(loc3, tyof3, rator, rands)):
      formula_match(loc, vars, goal_rator, rator, matching, env)
      for (goal_rand, rand) in zip(goal_rands, rands):
          new_goal_rand = goal_rand.substitute(matching)
          formula_match(loc, vars, new_goal_rand, rand, matching, env)
    case (And(loc2, tyof2, goal_args),
          And(loc3, tyof3, args)):
      for (goal_arg, arg) in zip(goal_args, args):
          new_goal_arg = goal_arg.substitute(matching)
          formula_match(loc, vars, new_goal_arg, arg, matching, env)
    case (Or(loc2, tyof2, goal_args),
          Or(loc3, tyof3, args)):
      for (goal_arg, arg) in zip(goal_args, args):
          new_goal_arg = goal_arg.substitute(matching)
          formula_match(loc, vars, new_goal_arg, arg, matching, env)
    case (IfThen(loc2, tyof2, goal_prem, goal_conc),
          IfThen(loc3, tyof3, prem, conc)):
      formula_match(loc, vars, goal_prem, prem, matching, env)
      new_goal_conc = goal_conc.substitute(matching)
      formula_match(loc, vars, new_goal_conc, conc, matching, env)
    # UNDER CONSTRUCTION
    case _:
      red_goal = goal_frm.reduce(env)
      red_frm = frm.reduce(env)
      if red_goal != red_frm:
          error(loc, "formula: " + str(red_frm) + "\n" \
                + "does not match expected formula: " + str(red_goal))
    
def type_match(loc, tyvars, param_ty, arg_ty, matching):
  if get_verbose():
    print("type_match(" + str(param_ty) + "," + str(arg_ty) + ")")
    print("\tin  " + ', '.join([str(x) for x in tyvars]))
    print("\twith " + str(matching))
  match (param_ty, arg_ty):
    case (Var(l1, t1, n1, rs1), Var(l2, t2, n2, rs2)) if n1 == n2:
      pass
    case (Var(l1, t1, name, rs1), _) if param_ty in tyvars:
      if name in matching.keys():
        type_match(loc, tyvars, matching[name], arg_ty, matching)
      else:
        if get_verbose():
            print('matching ' + name + ' := ' + str(arg_ty))
        matching[name] = arg_ty
    case (FunctionType(l1, tv1, pts1, rt1), FunctionType(l2, tv2, pts2, rt2)) \
        if len(tv1) == len(tv2) and len(pts1) == len(pts2):
      for (pt1, pt2) in zip(pts1, pts2):
        type_match(loc, tyvars, pt1, pt2, matching)
      type_match(loc, tyvars, rt1, rt2, matching)
    case (TypeInst(l1, n1, args1), TypeInst(l2, n2, args2)):
      if n1 != n2 or len(args1) != len(args2):
        error(loc, str(arg_ty) + " does not match " + str(param_ty))
      for (arg1, arg2) in zip(args1, args2):
        type_match(loc, tyvars, arg1, arg2, matching)
    # How to handle GenericUnknownInst?
    case (TypeInst(l1, n1, args1), GenericUnknownInst(l2, n2)):
      if n1 != n2:
        error(loc, str(arg_ty) + " does not match " + str(param_ty))
    case _:
      if param_ty != arg_ty:
        error(loc, str(arg_ty) + " does not match " + str(param_ty))

def type_names(loc, names):
  index = 0
  result = []
  for n in reversed(names):
    result.insert(0, Var(loc, None, n, []))
    index += 1
  return result

def type_check_call_funty(loc, new_rator, args, env, recfun, subterms, ret_ty,
                          call, typarams, param_types, return_type):
  if len(args) != len(param_types):
    error(loc, 'incorrect number of arguments in call:\n\t' + str(call) \
          + '\n\texpected ' + str(len(param_types)) \
          + ' argument, not ' + str(len(args)))
  if len(typarams) == 0:
    #print('type check call to regular: ' + str(call))
    new_args = []
    for (param_type, arg) in zip(param_types, args):
      new_args.append(type_check_term(arg, param_type, env, recfun, subterms))
    if ret_ty != None and ret_ty != return_type:
      error(loc, 'expected ' + str(ret_ty) + ' but the call returns ' + str(return_type))
    return Call(loc, return_type, new_rator, new_args)
  else:
    #print('type check call to generic: ' + str(call))
    matching = {}
    # If there is an expected return type, match that first.
    type_params = type_names(loc, typarams)
    if ret_ty:
      try:
          type_match(loc, type_params, return_type, ret_ty, matching)
      except Exception as e:
        new_msg = 'expected type ' + str(ret_ty) + '\n' \
            + '\tbut the call ' + str(call) + '\n' \
            + '\thas return type ' + str(return_type) + '\n\n' \
            + '\tinferred type arguments: ' \
            + ', '.join([base_name(x) + ' := ' + str(ty) \
                         for (x,ty) in matching.items()])
        error(call.location, new_msg)
          
    # If we have already deduced the type parameters in the parameter type,
    # then we can check the term. Otherwise, we synthesize the term's type
    # and match it against the parameter type.
    try:
      new_args = []
      for (arg, param_ty) in zip(args, param_types):
          param_type = param_ty.substitute(matching)
          fvs = param_type.free_vars()\
                          .intersection(set([ty.name for ty in type_params]))
          if get_verbose():
            print('arg = ' + str(arg))
            print('param_type = ' + str(param_type))
            print('fvs = ' + ', '.join([base_name(x) for x in fvs]) + '\n')
          if len(fvs) == 0:
            new_arg = type_check_term(arg, param_type, env, recfun, subterms)
          else:
            new_arg = type_synth_term(arg, env, recfun, subterms)
            type_match(loc, type_params, param_type, new_arg.typeof, matching)
          new_args.append(new_arg)
    except Exception as e:
        new_msg = str(e) + '\n\n\t' + 'in context of call ' + str(call) + '\n' \
            + '\tfunction type: ' + str(FunctionType(loc, typarams, param_types,
                                                     return_type)) + '\n' \
            + '\tinferred type arguments: ' \
            + ', '.join([base_name(x) + ' := ' + str(ty) for (x,ty) in matching.items()])
        raise Exception(new_msg)
    
    # Were all the type parameters deduced?
    for x in typarams:
        if x not in matching.keys():
            error(loc, 'in call ' + str(call) \
                  + '\n\tcould not deduce a type for ' \
                  + base_name(x) + ' to instantiate ' + str(call.rator) \
                  + '\n\twhose type is: ' + str(new_rator.typeof))

    type_args = [matching[x] for x in typarams]
    inst_params = [p.substitute(matching) for p in param_types]
    inst_return_type = return_type.substitute(matching)
    inst_funty = FunctionType(loc, [], inst_params, inst_return_type)
    inst_rator = TermInst(loc, inst_funty, new_rator, type_args, True)
    return Call(loc, inst_return_type, inst_rator, new_args)

def type_check_call_helper(loc, new_rator, args, env, recfun, subterms, ret_ty, call):
  if get_verbose():
      print('tc_call_helper(' + str(call) + ') rator type: ' + str(new_rator.typeof))
  funty = new_rator.typeof
  match funty:
    case OverloadType(loc2, overloads):
      num_matches = 0
      for (x, funty) in overloads:
          match funty:
            case FunctionType(loc2, typarams, param_types, return_type):
              try:
                new_call = type_check_call_funty(loc, Var(loc2, funty, x, []), args, env, recfun,
                                                 subterms, ret_ty, call,
                                                 typarams, param_types, return_type)
                num_matches += 1
              except Exception as e:
                pass
      if num_matches == 0:
          error(loc, 'could not find a match for function call ' \
                + str(call) + '\n'\
                + 'overloads:\n\t' \
                + '\n\t'.join([str(ty) for (x,ty) in overloads]))
      elif num_matches > 1:
          error(loc, 'in call to ' + str(new_rator) + '\n'\
                + 'ambiguous overloads:\n' \
                + '\n'.join([error_header(ty.location) + str(ty) for (x,ty) in overloads]))
      else:
          return new_call
    case FunctionType(loc2, typarams, param_types, return_type):
      return type_check_call_funty(loc, new_rator, args, env, recfun, subterms, ret_ty, call,
                                   typarams, param_types, return_type)
    case _:
      error(loc, 'expected operator to have function type, not ' + str(funty))
      
def type_check_call(loc, rator, args, env, recfun, subterms, ret_ty, call):
  if get_verbose():
      print('tc_check_call(' + str(call) + ')')
      print('rator: ' + str(rator))
  new_rator = type_synth_term(rator, env, recfun, subterms)
  return type_check_call_helper(loc, new_rator, args, env, recfun, subterms, ret_ty, call)

def type_check_rec_call(loc, tvar, args, env, recfun, subterms, ret_ty, call):
  if get_verbose():
      print('tc_rec_call(' + str(call) + ')')
  match args[0]:
    case Var(loc3, tyof, arg_name, rs):
        if not (arg_name in subterms):
          error(loc, "ill-formed recursive call\n" \
                + "expected first argument to be " \
                + " or ".join([base_name(x) for x in subterms]) \
                + ", not " + base_name(arg_name))
    case _:
      error(loc, "ill-formed recursive call\n" \
            + "expected first argument to be " \
            + " or ".join([base_name(x) for x in subterms]) \
            + ", not " + str(args[0]))
  return type_check_call(loc, tvar, args, env, recfun, subterms, ret_ty, call)

# well-formed types
def check_type(typ, env):
  match typ:
    case Var(loc, tyof, name, rs):
      if not env.type_var_is_defined(typ):
        error(loc, 'undefined type variable ' + str(typ) + \
              '\nin environment:\n' + str(env))
      if len(rs) == 1:
          typ.name = rs[0]
      elif len(rs) == 0:
          pass
      else:
          error(loc, 'type names may not be overloaded ' + str(typ))
    case IntType(loc):
      pass
    case BoolType(loc):
      pass
    case TypeType(loc):
      pass
    case FunctionType(loc, typarams, param_types, return_type):
      env = env.declare_type_vars(loc, typarams)
      for ty in param_types:
        check_type(ty, env)
      check_type(return_type, env)
    case TypeInst(loc, typ, arg_types):
      check_type(typ, env)
      for ty in arg_types:
        check_type(ty, env)
    case GenericUnknownInst(loc, typ):
      check_type(typ, env)
    case ArrayType(loc, elt_type):
      check_type(elt_type, env)
    case _:
      print('error in check_type: unhandled type ' + repr(typ) + ' ' + str(type(typ)))
      exit(-1)

def type_first_letter(typ):
  match typ:
    case Var(loc, tyof, name, rs):
      return name[0]
    case IntType(loc):
      return 'i'
    case BoolType(loc):
      return 'b'
    case TypeType(loc):
      return 't'
    case FunctionType(loc, typarams, param_types, return_type):
      return 'f'
    case TypeInst(loc, typ, arg_types):
      return type_first_letter(typ)
    case GenericUnknownInst(loc, typ):
      return type_first_letter(typ)
    case _:
      print('error in type_first_letter: unhandled type ' + repr(typ))
      exit(-1)

def type_check_term_inst(loc, subject, tyargs, inferred, recfun, subterms, env):
  for ty in tyargs:
      check_type(ty, env)
  new_subject = type_synth_term(subject, env, recfun, subterms)
  ty = new_subject.typeof
  match ty:
    case Var(loc2, ty2, name, rs):
      retty = TypeInst(loc, name, tyargs)
    case FunctionType(loc2, typarams, param_types, return_type):
      sub = {x: t for (x,t) in zip(typarams, tyargs)}
      inst_param_types = [t.substitute(sub) for t in param_types]
      inst_return_type = return_type.substitute(sub)
      retty = FunctionType(loc2, [], inst_param_types, inst_return_type)
    case GenericUnknownInst(loc2, union_type):
      retty = TypeInst(loc2, union_type, tyargs)
    case _:
      error(loc, 'expected a type name, not ' + str(ty))
  return TermInst(loc, retty, new_subject, tyargs, inferred)

def type_check_term_inst_var(loc, subject_var, tyargs, inferred, env):
  match subject_var:
    case Var(loc2, tyof, name, rs):
      for ty in tyargs:
          check_type(ty, env)
      ty = env.get_type_of_term_var(Var(loc2, tyof, name, rs))
      match ty:
        case Var(loc3, ty2, name, rs2):
          retty = TypeInst(loc, name, tyargs)
        case FunctionType(loc3, typarams, param_types, return_type):
          sub = {x: t for (x,t) in zip(typarams, tyargs)}
          inst_param_types = [t.substitute(sub) for t in param_types]
          inst_return_type = return_type.substitute(sub)
          retty = FunctionType(loc3, [], inst_param_types, inst_return_type)
        case GenericUnknownInst(loc3, union_type):
          retty = TypeInst(loc3, union_type, tyargs)
        case _:
          error(loc, 'cannot instantiate a term of type ' + str(ty))
      return TermInst(loc, retty, Var(loc2, tyof, rs[0], [rs[0]]), tyargs, inferred)
    case _:
      error(loc, 'internal error, expected variable, not ' + str(subject_var))

def type_synth_term(term, env, recfun, subterms):
  if get_verbose():
    print('type_synth_term: ' + str(term))
  match term:
    case Mark(loc, tyof, subject):
      new_subject = type_synth_term(subject, env, recfun, subterms)
      ret = Mark(loc, new_subject.typeof, new_subject)
  
    case Var(loc, _, name, rs):
      ty = env.get_type_of_term_var(term)
      if ty == None:
        error(loc, 'while type checking, undefined variable ' + str(term) \
              + '\nin scope:\n' + str(env))
      match ty:
        case GenericUnknownInst(loc2, union_type):
          error(loc, 'Cannot infer type arguments for\n' \
                + '\t' + base_name(name) + '\nPlease make them explicit.')
      
      #ret = Var(loc, ty, name, rs)
      if len(rs) == 1:
          ret = Var(loc, ty, rs[0], [ rs[0] ])
      else:
          if get_verbose():
              print('type_synth_term(' + str(term) + ') waiting to resolve name')
          ret = Var(loc, ty, name, rs)
      
    case Generic(loc, _, type_params, body):
      body_env = env.declare_type_vars(loc, type_params)
      new_body = type_synth_term(body, body_env, recfun, subterms)
      match new_body.typeof:
        case FunctionType(loc2, [], param_types, return_type):
          ty = FunctionType(loc, type_params, param_types, return_type)
          ret = Generic(loc, ty, type_params, new_body)
        case _:
          error(loc, 'body of generic must be a function, not ' \
                + str(new_body.typeof))

    case Lambda(loc, _, params, body):
      for (p,t) in params:
          if t:
              check_type(t, env)
      vars = [p for (p,t) in params]
      param_types = [t for (p,t) in params]
      if any([t == None for t in param_types]):
          error(loc, 'Cannot synthesize a type for ' + str(term) + '.\n'\
                + 'Add type annotations to the parameters.')
      body_env = env.declare_term_vars(loc, params)
      new_body = type_synth_term(body, body_env, recfun, subterms)
      typ = FunctionType(loc, [], param_types, new_body.typeof)
      return Lambda(loc, typ, params, new_body)
      
    case TLet(loc, _, var, rhs, body):
      new_rhs = type_synth_term(rhs, env, recfun, subterms)
      body_env = env.declare_term_var(loc, var, new_rhs.typeof)
      new_body = type_synth_term(body, body_env, recfun, subterms)
      ret = TLet(loc, new_body.typeof, var, new_rhs, new_body)
  
    case Conditional(loc, _, cond, thn, els):
      new_cond = type_check_term(cond, BoolType(loc), env, recfun, subterms)
      new_thn = type_synth_term(thn, env, recfun, subterms)
      new_els = type_synth_term(els, env, recfun, subterms)
      if new_thn.typeof != new_els.typeof:
        error(loc, 'conditional expects same type for the two branches'\
              + ' but ' + str(new_thn.typeof) + ' ≠ ' + str(new_els.typeof))
      ret = Conditional(loc, new_thn.typeof, new_cond, new_thn, new_els)
      
    case Int(loc, _, value):
      ty = IntType(loc)
      ret = Int(loc, ty, value)
      
    case Bool(loc, _, value):
      ty = BoolType(loc)
      ret = Bool(loc, ty, value)
      
    case And(loc, _, args):
      new_args = [check_formula(arg, env) for arg in args]
      ty = BoolType(loc)
      ret = And(loc, ty, new_args)
      
    case Or(loc, _, args):
      new_args = [check_formula(arg, env) for arg in args]
      ty = BoolType(loc)
      ret = Or(loc, ty, new_args)
      
    case IfThen(loc, _, prem, conc):
      new_prem = check_formula(prem, env)
      new_conc = check_formula(conc, env)
      ty = BoolType(loc)
      ret = IfThen(loc, ty, new_prem, new_conc)
      
    case All(loc, _, var, pos, body):
      all_types = None
      x, ty = var
      check_type(ty, env)
      if isinstance(ty, TypeType):
        if all_types == None or all_types == True:
          all_types = True
        else:
          error(loc, 'cannot mix type and term variables in an all formula')
      else:
        if all_types == None or all_types == False:
          all_types = False
        else:
          error(loc, 'cannot mix type and term variables in an all formula')
      body_env = env.declare_term_vars(loc, [var])
      new_body = check_formula(body, body_env)      
      ty = BoolType(loc)
      ret = All(loc, ty, var, pos, new_body)
  
    case Some(loc, _, vars, body):
      for (x,ty) in vars:
          check_type(ty, env)
      body_env = env.declare_term_vars(loc, vars)
      new_body = check_formula(body, body_env)
      ty = BoolType(loc)
      ret = Some(loc, ty, vars, new_body)
      
    case MakeArray(loc, _, arg):
      lst = type_synth_term(arg, env, recfun, subterms)
      match lst.typeof:
        case TypeInst(loc2, lst_ty, [elt_type]):
          union_def = lookup_union(loc, lst_ty, env)
          if base_name(union_def.name) == 'List':
            ret = MakeArray(loc, ArrayType(loc, elt_type), lst)
          else:
            error(loc, 'expected List, not union ' + union_def.name)
        case _:
          error(loc, 'expected List, not ' + str(lst.typeof))

    case ArrayGet(loc, _, array, index):
      new_array = type_synth_term(array, env, recfun, subterms)
      new_index = type_synth_term(index, env, recfun, subterms)
      match new_array.typeof:
        case ArrayType(loc2, elt_type):
          ret = ArrayGet(loc, elt_type, new_array, new_index)
        case _:
          error(loc, 'expected an array, not ' + str(new_array.typeof))
          
    case Call(loc, _, Var(loc2, ty2, name, rs), args) \
        if name == '=' or name == '≠':
      lhs = type_synth_term(args[0], env, recfun, subterms)
      rhs = type_check_term(args[1], lhs.typeof, env, recfun, subterms)
      ty = BoolType(loc)
      ret = Call(loc, ty, Var(loc2, ty2, name, rs), [lhs, rhs])
        
    case Call(loc, _, Var(loc2, ty2, name, rs), args) if name == recfun:
      # recursive call
      ret = type_check_rec_call(loc, Var(loc2, ty2, name, rs), args, env,
                                recfun, subterms, None, term)
      
    case Call(loc, _, rator, args):
      # non-recursive call
      ret = type_check_call(loc, rator, args, env, recfun, subterms, None, term)
      
    case Switch(loc, _, subject, cases):
      new_subject = type_synth_term(subject, env, recfun, subterms)
      ty = new_subject.typeof

      cases_present = {}
      result_type = [None] # boxed to allow mutable update in process_case

      def process_case(c, result_type, cases_present):
        new_env = check_pattern(c.pattern, ty, env, cases_present)
        new_body = type_synth_term(c.body, new_env, recfun, subterms)
        case_type = new_body.typeof
        if result_type[0] == None:
          result_type[0] = case_type
        elif case_type != result_type[0]:
          error(c.location, 'bodies of cases must have same type, but ' \
                + str(case_type) + ' ≠ ' + str(result_type[0]))
        return SwitchCase(c.location, c.pattern, new_body)

      new_cases = [process_case(c, result_type, cases_present) \
                   for c in cases]
      ret = Switch(loc, result_type[0], new_subject, new_cases)
      
      # check exhaustiveness
      match ty:
        case BoolType(loc2):
          has_true_case = False
          has_false_case = False
          for scase in cases:
            match scase.pattern:
              case PatternBool(l1, True):
                has_true_case = True
              case PatternBool(l1, False):
                has_false_case = True
              case _:
                raise Exception('not an appropraite case for bool\n\t' \
                                + str(scase))
          if not has_true_case:
            error(loc, 'missing case for true')
          if not has_false_case:
            error(loc, 'missing case for false')
        case _:
          dfn = lookup_union(loc, ty, env)
          match dfn:
            case Union(loc2, name, typarams, alts):
              for alt in alts:
                  if alt.name not in cases_present.keys():
                      error(loc, 'this switch is missing a case for: ' \
                            + str(alt))
            case _:
              error(loc, 'expected a union type, not ' + str(ty))

    case TermInst(loc, _, Var(loc2, tyof, name, rs), tyargs, inferred):
      ret = type_check_term_inst_var(loc, Var(loc2, tyof, name, rs), tyargs,
                                     inferred, env)
      
    case TermInst(loc, _, subject, tyargs, inferred):
      ret = type_check_term_inst(loc, subject, tyargs, inferred, recfun, subterms, env)
          
    case TAnnote(loc, tyof, subject, typ):
      check_type(typ, env)
      ret = type_check_term(subject, typ, env, recfun, subterms)

    case RecFun(loc, name, typarams, params, returns, cases):
      fun_type = FunctionType(loc, typarams, params, returns)
      ret = term
      term.typeof = fun_type
      
    case _:
      if isinstance(term, Type):
        error(term.location, 'type_synth_term called on type ' + str(term))
        ret = TypeType(term.location)
      else:
        error(term.location, 'cannot synthesize a type for ' + str(term))
  if get_verbose():
    print('\t' + str(term) + '\n\t=> ' + str(ret) + ' : ' + str(ret.typeof))
  return ret

def type_check_formula(term, env):
  return type_check_term(term, BoolType(term.location), env, None, [])

def type_check_term(term, typ, env, recfun, subterms):
  if get_verbose():
    print('type_check_term: ' + str(term) + ' : ' + str(typ) + '?')
  match term:
    case Mark(loc, tyof, subject):
      new_subject = type_check_term(subject, typ, env, recfun, subterms)
      return Mark(loc, new_subject.typeof, new_subject)
    case Hole(loc, tyof):
      #return Hole(loc, BoolType(loc))
      return Hole(loc, typ)
    case Omitted(loc, tyof):
      return Omitted(loc, typ)
    case Generic(loc, _, type_params, body):
      match typ:
        case FunctionType(loc2, type_params2, param_types2, return_type2):
          sub = {U: Var(loc, None, T, [T]) \
                 for (T,U) in zip(type_params, type_params2) }
          new_param_types = [ty.substitute(sub) for ty in param_types2]
          new_return_type = return_type2.substitute(sub)
          body_env = env.declare_type_vars(loc, type_params)
          funty = FunctionType(loc2, [], new_param_types, new_return_type)
          new_body = type_check_term(body, funty, body_env, recfun, subterms)
          return Generic(loc, typ, type_params, new_body)
        case _:
          error(loc, 'expected a generic term, not ' + str(term))
        
    case Var(loc, _, name, rs):
      var_typ = env.get_type_of_term_var(term)
      if get_verbose():
          print('var_typ = ' + str(var_typ))
      if var_typ == None:
        error(loc, 'undefined variable ' + str(term) \
              + '\nin scope:\n' + str(env))
      match (var_typ, typ):
        case (OverloadType(loc2, overloads), _):
          for (x, ty) in overloads:
              if ty == typ:
                  if get_verbose():
                      print('found overload ' + x + ' of type ' + str(typ))
                  return Var(loc, typ, x, [x])
          error(loc, 'could not find an overload of ' + name \
                + ' of type ' + str(typ) + '\nin: ' + str(var_typ))
        case (GenericUnknownInst(loc2, union1), TypeInst(loc3, union2, tyargs)):
          if union1 == union2:
              return TermInst(loc, typ, Var(loc, typ, rs[0], [rs[0]]),
                              tyargs, True)
        case (FunctionType(loc1, typarams, param_types1, ret_type1),
              FunctionType(loc2, [], param_types2, ret_type2)):
          if len(typarams) > 0:
            matching = {}
            type_params = type_names(loc, typarams)
            try:
              type_match(loc, type_params, ret_type1, ret_type2, matching)
              for (p1, p2) in zip(param_types1, param_types2):
                  type_match(loc, type_params, p1, p2, matching)
              type_args = [matching[x] for x in type_params]
              return TermInst(Var(loc, var_typ, rs[0], [rs[0]]),
                              type_args, True)
            except Exception as e:
              pass
      if var_typ == typ:
        if len(rs) > 0:
            return Var(loc, typ, rs[0], [ rs[0] ])
        else:
            return Var(loc, typ, name, [name])
      else:
        error(loc, 'expected a term of type ' + str(typ) \
              + '\nbut got term ' + str(term) + ' of type ' + str(var_typ))
  
    case Lambda(loc, _, params, body):
      match typ:
        case FunctionType(loc2, [], param_types, return_type):
          vars = [n for (n,t) in params]
          body_env = env.declare_term_vars(loc, zip(vars, param_types))
          new_body = type_check_term(body, return_type, body_env,
                                     recfun, subterms)
          return Lambda(loc, typ, params, new_body)
        case FunctionType(loc2, ty_params, _, _):
          pretty_params = ", ".join([base_name(x) for x in ty_params])
          plural = 's' if len(ty_params) > 1 else ''

          error(loc, f'Expected type parameter{plural} {pretty_params}, but got a lambda.\n\t' + \
                f'Add generic {pretty_params} {"{ ... }"} around the function body.')
        case _:
          error(loc, 'expected a term of type ' + str(typ) + '\n'\
                + 'but instead got a lambda')
          
    case TLet(loc, _, var, rhs, body):
      new_rhs = type_synth_term(rhs, env, recfun, subterms)
      body_env = env.declare_term_var(loc, var, new_rhs.typeof)
      new_body = type_check_term(body, typ, body_env, recfun, subterms)
      return TLet(loc, typ, var, new_rhs, new_body)
      
    case Call(loc, _, Var(loc2, vt, name, rs), args) \
        if name == '=' or name == '≠':
      new_term = type_synth_term(term, env, recfun, subterms)
      ty = new_term.typeof
      if ty != typ:
        error(term.location, 'expected term of type ' + str(typ) \
              + ' but got ' + str(ty))
      return new_term
      
    case Call(loc, _, Var(loc2, vty, name, rs), args) if name == recfun:
      # recursive call
      return type_check_rec_call(loc, Var(loc2, vty, name, rs), args, env,
                                 recfun, subterms, typ, term)
  
    case Call(loc, _, rator, args):
      # non-recursive call
      return type_check_call(loc, rator, args, env, recfun, subterms, typ, term)

    case Switch(loc, _, subject, cases):
      new_subject = type_synth_term(subject, env, recfun, subterms)
      ty = new_subject.typeof
      cases_present = {}
      result_type = [None] # boxed to allow mutable update in process_case
      
      def process_case(c, result_type, cases_present):
        new_env = check_pattern(c.pattern, ty, env, cases_present)
        new_body = type_check_term(c.body, typ, new_env, recfun, subterms)
        case_type = new_body.typeof
        if result_type[0] == None:
          result_type[0] = case_type
        elif case_type != result_type[0]:
          error(c.location, 'bodies of cases must have same type, but ' \
                + str(case_type) + ' ≠ ' + str(result_type[0]))
        return SwitchCase(c.location, c.pattern, new_body)

      new_cases = [process_case(c, result_type, cases_present) for c in cases]

      # Check case coverage
      match ty:
        case BoolType(loc2):
          if 'True' not in cases_present.keys():
            error(loc, 'missing case for true')
          if 'False' not in cases_present.keys():
            error(loc, 'missing case for false')
        case _:
          dfn = lookup_union(loc, ty, env)
          match dfn:
            case Union(loc2, name, typarams, alts):
              for alt in alts:
                  if alt.name not in cases_present.keys():
                      error(loc, 'missing a case for:\n\t' \
                            + str(alt))
            case _:
              error(loc, 'expected a union type, not ' + str(ty))
      
      return Switch(loc, result_type[0], new_subject, new_cases)
      
    case Conditional(loc, _, cond, thn, els):
      new_cond = type_check_term(cond, BoolType(loc), env, recfun, subterms)
      new_thn = type_check_term(thn, typ, env, recfun, subterms)
      new_els = type_check_term(els, typ, env, recfun, subterms)
      return Conditional(loc, typ, new_cond, new_thn, new_els)
  
    case TermInst(loc, _, Var(loc2, tyof, name, rs), tyargs, inferred):
      return type_check_term_inst_var(loc, Var(loc2, tyof, name, rs), tyargs,
                                      inferred, env)
      
    case TermInst(loc, _, subject, tyargs, inferred):
      return type_check_term_inst(loc, subject, tyargs, inferred, recfun, subterms, env)
  
    case _:
      if get_verbose():
          print('type_check_term delegating to type_synth_term')
      new_term = type_synth_term(term, env, recfun, subterms)
      ty = new_term.typeof
      if ty != typ:
        error(term.location, 'expected term of type ' + str(typ) \
              + ' but got ' + str(ty))
      return new_term
  
def lookup_union(loc, typ, env):
  tyname = None
  match typ:
    case Var(loc2, vty, name, rs):
      tyname = typ
    case TypeInst(loc2, inst_typ, tyargs):
      tyname = inst_typ
    case _:
      error(loc, 'expected a union type but instead got ' + str(typ))
  return env.get_def_of_type_var(tyname)

def check_constructor_pattern(loc, pat_constr, params, typ, env, cases_present):
  if get_verbose():
    print('check_constructor_pattern: ' + str(pat_constr))
  defn = lookup_union(loc, typ, env)
  if get_verbose():
    print('for union: ' + str(defn))
  match defn:
    case Union(loc2, name, typarams, alts):
      # example:
      # typ is List<E>
      # union List<T> { empty; node(T, List<T>); }
      # pat_constr == node
      found_pat_constr = False
      for constr in alts:
        # constr = node(T, List<T>)
        if constr.name in pat_constr.resolved_names:
          pat_constr.name = constr.name
          if len(typarams) > 0:
            sub = { T: ty for (T,ty) in zip(typarams, typ.arg_types)}
            parameter_types = [p.substitute(sub) for p in constr.parameters]
          else:
            parameter_types = constr.parameters
          #print('pattern variables: ' + str(list(zip(params, parameter_types))))
          env = env.declare_term_vars(loc2, zip(params, parameter_types))
          cases_present[constr.name] = True
          found_pat_constr = True
      if not found_pat_constr:
          error(loc, base_name(pat_constr.name) + ' is not a constructor of union ' + str(defn))
      return env
    case _:
      error(loc, str(typ) + ' is not a union type')
        
def check_pattern(pattern, typ, env, cases_present):
  if get_verbose():
    print('check pattern: ' + str(pattern))
    print('against type: ' + str(typ))
    #print('in env: ' + str(env))
#  pattern.typeof = typ
  match pattern:
    case PatternBool(loc, value):
      match typ:
        case BoolType(loc2):
          cases_present[str(value)] = True
          return env
        case _:
          error(pattern.location, 'expected a pattern of type\n\t' \
                + str(typ) + '\nbut got\n\t' + str(pattern))
    case PatternCons(loc, constr, params):
      return check_constructor_pattern(loc, constr, params, typ, env,
                                       cases_present)
    case _:
      error(pattern.location, 'expected a pattern, not\n\t' \
            + str(pattern))

def check_formula(frm, env):
  return type_check_term(frm, BoolType(frm.location), env, None, [])

modules = set()

def process_declaration(stmt, env):
  if get_verbose():
    print('process_declaration(' + str(stmt) + ')')
  match stmt:
    case Define(loc, name, ty, body):
      if ty == None:
        new_body = type_synth_term(body, env, None, [])
        new_ty = new_body.typeof
      else:
        check_type(ty, env)
        new_body = body
        new_ty = ty

      # Only allow overloading of functions
      unique_name = {base_name(n): n for n in env.dict.keys()}
      orig_name = base_name(name)
      if orig_name in unique_name.keys():
          match new_ty:
            case FunctionType(loc2, ty_params, params, ret_ty):
              pass
            case _:
              binding = env.dict[unique_name[orig_name]]
              error(loc, 'the name ' + orig_name + ' is already defined:\n' \
                    + error_header(binding.location) \
                    + ' ' + orig_name + ' : ' + str(binding) + '\n' \
                    + 'Only functions may have multiple definitions with the same name.')
        
      return Define(loc, name, new_ty, new_body), \
              env.declare_term_var(loc, name, new_ty)
          
    case Theorem(loc, name, frm, pf, isLemma):
      return stmt, env
  
    case RecFun(loc, name, typarams, params, returns, cases):
      body_env = env.declare_type_vars(loc, typarams)
      check_type(returns, body_env)
      for t in params:
          check_type(t, body_env)
      fun_type = FunctionType(loc, typarams, params, returns)
      return stmt, env.declare_term_var(loc, name, fun_type)
      
    case Union(loc, name, typarams, alts):
      env = env.define_type(loc, name, stmt)
      union_type = Var(loc, None, name, [name])
      body_env = env.declare_type_vars(loc, typarams)
      body_union_type = union_type
      new_alts = []
      for constr in alts:
        if len(constr.parameters) > 0:
          if len(typarams) > 0:
            tyvars = [Var(loc, None, p, [p]) for p in typarams]
            return_type = TypeInst(loc, body_union_type, tyvars)
          else:
            return_type = body_union_type
          for ty in constr.parameters:
            check_type(ty, body_env)
          constr_type = FunctionType(constr.location, typarams,
                                     constr.parameters, return_type)
        elif len(typarams) > 0:
          constr_type = GenericUnknownInst(loc, union_type)
        else:
          constr_type = union_type

        new_constr = constr
        env = env.declare_term_var(loc, constr.name, constr_type)
        new_alts.append(new_constr)
        
      return Union(loc, name, typarams, new_alts), env
  
    case Import(loc, name, ast):
      old_verbose = get_verbose()
      if get_verbose() == VerboseLevel.CURR_ONLY:
        set_verbose(VerboseLevel.NONE)

      if name in imported_modules:
          set_verbose(old_verbose)
          return stmt, env
      else:
          imported_modules.add(name)
          ast2 = []
          for s in ast:
            new_s, env = process_declaration(s, env)
            ast2.append(new_s)

          ast3 = []
          for s in ast2:
            new_s = type_check_stmt(s, env)
            ast3.append(new_s)

          for s in ast3:
            env = collect_env(s, env)
            
          if name not in checked_modules:
            for s in ast3:
              check_proofs(s, env)
            checked_modules.add(name)  

          set_verbose(old_verbose)
          return Import(loc, name, ast3), env
  
    case Assert(loc, frm):
      return stmt, env
  
    case Print(loc, trm):
      return stmt, env
  
    case _:
      error(stmt.location, "unrecognized statement:\n" + str(stmt))

def type_check_fun_case(fun_case, name, params, returns, body_env, cases_present):
    body_env = check_pattern(fun_case.pattern, params[0], body_env, cases_present)
    if len(fun_case.parameters) != len(params[1:]):
      error(fun_case.location, 'incorrect number of parameters, '\
            + 'expected ' + str(len(params)))
    body_env = body_env.declare_term_vars(fun_case.location,
                                          zip(fun_case.parameters, params[1:]))
    match fun_case.pattern:
      case PatternCons(loc, cons, parameters):
        pat_params = parameters
      case PatternBool(loc, val):
        pat_params = []
    new_body = type_check_term(fun_case.body, returns, body_env, name, pat_params)
    return FunCase(fun_case.location, fun_case.pattern, fun_case.parameters, new_body)

def type_check_stmt(stmt, env):
  if get_verbose():
    print('type_check_stmt(' + str(stmt) + ')')
    #print('env: ' + str(env))
  match stmt:
    case Define(loc, name, ty, body):
      if ty == None:
        new_body = body # already type checked in process_declaration
        new_ty = body.typeof
      else:
        new_body = type_check_term(body, ty, env, None, [])
        new_ty = ty
      return Define(loc, name, new_ty, new_body)
        
    case Theorem(loc, name, frm, pf, isLemma):
      new_frm = check_formula(frm, env)
      return Theorem(loc, name, new_frm, pf, isLemma)
  
    case RecFun(loc, name, typarams, params, returns, cases):
      # alpha rename the type parameters in the function's type
      new_typarams = [generate_name(t) for t in typarams]
      sub = {x: Var(loc, None, y, [y]) for (x,y) in zip(typarams, new_typarams)}
      new_params = [p.substitute(sub) for p in params]
      new_returns = returns.substitute(sub)
      fun_type = FunctionType(loc, new_typarams, new_params, new_returns)
      
      env = env.define_term_var(loc, name, fun_type, stmt.reduce(env))
      cases_present = {}
      body_env = env.declare_type_vars(loc, typarams)
      new_cases = [type_check_fun_case(c, name, params, returns, body_env,
                                       cases_present) \
                   for c in cases]
        
      # check for completeness of cases
      uniondef = lookup_union(params[0].location, params[0], env)
      for c in uniondef.alternatives:
        if not c.name in cases_present.keys():
          error(loc, 'missing function case for ' + base_name(c.name))

      new_recfun = RecFun(loc, name, typarams, params, returns, new_cases)
      return new_recfun
          
    case Union(loc, name, typarams, alts):
      return stmt
  
    case Import(loc, name, ast):
      return stmt
  
    case Assert(loc, frm):
      new_frm = check_formula(frm, env)
      return Assert(loc, new_frm)
  
    case Print(loc, trm):
      new_trm = type_synth_term(trm, env, None, [])
      return Print(loc, new_trm)
  
    case _:
      error(stmt.location, "type checking, unrecognized statement:\n" + str(stmt))

def collect_env(stmt, env):
  match stmt:
    case Define(loc, name, ty, body):
      return env.define_term_var(loc, name, ty, body)
        
    case Theorem(loc, name, frm, pf, isLemma):
      return env.declare_proof_var(loc, name, frm)
  
    case RecFun(loc, name, typarams, params, returns, cases):
      fun_type = FunctionType(loc, typarams, params, returns)
      return env.define_term_var(loc, name, fun_type, stmt)
          
    case Union(loc, name, typarams, alts):
      return env
  
    case Import(loc, name, ast):
      return env
  
    case Assert(loc, frm):
      return env
  
    case Print(loc, trm):
      return env
  
    case _:
      error(stmt.location, "collect_env, unrecognized statement:\n" + str(stmt))
      
def check_proofs(stmt, env):
  if get_verbose():
    print('check_proofs(' + str(stmt) + ')')
    #print('env: ' + str(env))
  match stmt:
    case Define(loc, name, ty, body):
      pass
    case Theorem(loc, name, frm, pf, isLemma):
      if get_verbose():
        print('checking proof of theorem ' + base_name(name))
      check_proof_of(pf, frm, env)
      
    case RecFun(loc, name, typarams, params, returns, cases):
      pass
  
    case Union(loc, name, typarams, alts):
      pass
  
    case Import(loc, name, ast):
      pass
  
    case Print(loc, trm):
      set_reduce_all(True)
      result = trm.reduce(env)
      set_reduce_all(False)
      print(str(result))
      
    case Assert(loc, frm):
      match frm:
        case Call(loc2, tyof2, Var(loc3, tyof3, '=', rs3), [lhs, rhs]):
          set_reduce_all(True)
          L = lhs.reduce(env)
          R = rhs.reduce(env)
          set_reduce_all(False)
          if L == R:
            pass
          else:
              error(loc, 'assertion failed:\n' +
                    '\t' + str(L) + ' ≠ ' + str(R) + '\n')
        case _:
          set_reduce_all(True)
          result = frm.reduce(env)
          set_reduce_all(False)
          match result:
            case Bool(loc2, tyof, True):
              pass
            case Bool(loc2, tyof, False):
              error(loc, 'assertion failed: ' + str(frm))
            case result:
              error(loc, 'assertion expected Boolean result, not ' \
                    + str(result))
          
    case _:
      error(stmt.location, "unrecognized statement:\n" + str(stmt))
      
def check_deduce(ast, module_name):
  env = Env()
  ast2 = []
  imported_modules.clear()
  if get_verbose():
      print('--------- Processing Declarations ------------------------')
  for s in ast:
    new_s, env = process_declaration(s, env)
    ast2.append(new_s)
  if get_verbose():
    for s in ast2:
      print(s)

  if get_verbose():
    print('env:\n' + str(env))          
    print('--------- Type Checking ------------------------')
  ast3 = []
  for s in ast2:
    new_s = type_check_stmt(s, env)
    ast3.append(new_s)
  if get_verbose():
    for s in ast3:
      print(s)
      
  if get_verbose():
    print('--------- Proof Checking ------------------------')
  for s in ast3:
    env = collect_env(s, env)
  if get_verbose():
    print('env:\n' + str(env))  

  if module_name not in checked_modules:
    for s in ast3:
      check_proofs(s, env)
    checked_modules.add(module_name)  
