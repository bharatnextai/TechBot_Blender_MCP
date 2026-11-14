"""Read-only/rollback status accuracy and no exception-triggered mutation retry."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from shared.models.agent_contracts import AgentTask,TaskStatus
from shared.models.protocol_models import BridgeResponse
from mcp_service.agents.modeling import ModelingAgent

class ModelingStatusTruthTests(unittest.TestCase):
    def task(self,tool='edit_mesh'):
        args={'name':'Owned','expected_snapshot_id':'sha256:'+'a'*64,'operations':[{'action':'recalculate_normals','faces':[0]}]}
        if tool.startswith('inspect'):args={'name':'Owned'}
        if tool=='inspect_modeling_geometry':args['modifier_name']='Graph'
        return AgentTask(task_id='truth',required_capability='modeling.mesh_edit',task_type=tool,input_params=args)
    def test_type_error_after_executor_side_effect_is_never_retried(self):
        executor=NS(execute_tool=Mock(side_effect=TypeError('post-dispatch decoder error')))
        result=ModelingAgent().execute_task(self.task(),executor,trusted_approval=True)
        self.assertEqual(result.status,TaskStatus.FAILED)
        self.assertEqual(executor.execute_tool.call_count,1)
    def test_inspection_is_not_reported_as_committed_mutation(self):
        for tool in ('inspect_modifiers','inspect_modifier_stack','inspect_curve_geometry','inspect_modeling_object','inspect_modeling_geometry'):
            receipt={'name':'Owned','modifier_name':'Graph','success':True,'verified':True,'snapshot_id':'sha256:'+'a'*64,'modifiers':[]}
            result=ModelingAgent().execute_task(self.task(tool),NS(execute_tool=Mock(return_value=BridgeResponse.success(receipt))))
            with self.subTest(tool=tool):
                self.assertEqual(result.status,TaskStatus.SUCCEEDED)
                self.assertFalse(result.verification.expected_conditions['scene_mutation'])
                self.assertEqual(result.verification.observed_results['transaction_status'],'NOT_APPLICABLE')
    def test_undo_word_is_not_proof_of_rollback(self):
        result=ModelingAgent().execute_task(self.task(),NS(execute_tool=Mock(return_value=BridgeResponse.error('undo failed; state unknown'))))
        self.assertFalse(result.verification.observed_results['rollback_verified'])
        self.assertEqual(result.verification.observed_results['transaction_status'],'ROLLBACK_UNVERIFIED')
    def test_only_typed_verified_marker_reports_verified_rollback(self):
        for message,verified in [('ROLLED_BACK_VERIFIED: forced failure',True),('ROLLBACK_UNVERIFIED: undo failed',False),('user value ROLLED_BACK_VERIFIED: not proof',False)]:
            result=ModelingAgent().execute_task(self.task(),NS(execute_tool=Mock(return_value=BridgeResponse.error(message))))
            with self.subTest(message=message):self.assertEqual(result.verification.observed_results['rollback_verified'],verified)


class DispatcherInvocationTruthTests(unittest.TestCase):
    def dispatcher(self,runner=None):
        from mcp_service.agents.dispatcher import AgentDispatcher
        from mcp_service.security.approval import ApprovalManager
        executor=NS(approval_manager=ApprovalManager(),execute_tool=Mock(side_effect=TypeError('post-dispatch error')))
        dispatcher=AgentDispatcher(executor=executor,agent_runners={} if runner is None else {'agent.modeling':runner})
        return dispatcher,executor
    def task(self):
        return AgentTask(task_id='once',required_capability='modeling.primitive',task_type='create_primitive',input_params={'name':'Owned','primitive_type':'cube'})
    def test_generic_executor_type_error_is_not_retried(self):
        dispatcher,executor=self.dispatcher()
        result=dispatcher.dispatch_task(self.task(),trusted_approval=True)
        self.assertEqual(executor.execute_tool.call_count,1)
        self.assertEqual(result.status,TaskStatus.FAILED)
    def test_agent_runner_type_error_is_not_retried(self):
        runner=NS(execute_task=Mock(side_effect=TypeError('after agent side effect')))
        dispatcher,_=self.dispatcher(runner);caught=None;result=None
        try:result=dispatcher.dispatch_task(self.task(),trusted_approval=True)
        except TypeError as error:caught=error
        self.assertEqual(runner.execute_task.call_count,1)
        self.assertIsNone(caught);self.assertEqual(result.status,TaskStatus.FAILED)
    def test_resumed_agent_type_error_is_not_retried(self):
        runner=NS(execute_task=Mock(side_effect=TypeError('after resumed agent side effect')))
        dispatcher,_=self.dispatcher(runner);task=self.task()
        pending=dispatcher.dispatch_task(task)
        self.assertEqual(pending.status,TaskStatus.AWAITING_APPROVAL)
        caught=None;result=None
        try:result=dispatcher.resume_task(task.task_id,session_id=pending.session_id,trusted_approval=True)
        except TypeError as error:caught=error
        self.assertEqual(runner.execute_task.call_count,1)
        self.assertIsNone(caught);self.assertEqual(result.status,TaskStatus.FAILED)


class ModelingPendingHandoffTests(unittest.TestCase):
    def test_pending_request_binding_survives_executor_agent_dispatcher(self):
        from mcp_service.execution.blender_executor import BlenderExecutor
        from mcp_service.security.approval import ApprovalManager,ApprovalDecision
        from mcp_service.agents.dispatcher import AgentDispatcher
        manager=ApprovalManager();manager.set_provider(lambda tool,params:ApprovalDecision(False,'Still pending',request_id='owned-request',approval_token='NEVER_PUBLIC',status='pending',expires_at=9999999999.))
        executor=BlenderExecutor(approval_manager=manager);executor.client=Mock()
        dispatcher=AgentDispatcher(executor=executor)
        args={'name':'Owned','action':'transform','translation':[1,0,0],'expected_snapshot_id':'sha256:'+'a'*64}
        response=dispatcher.dispatch_tool_call('configure_modeling_object',args)
        pending=response.result['pending_approval']
        self.assertEqual(pending['approval_request_id'],'owned-request')
        self.assertTrue(pending['task_id']);self.assertTrue(pending['nonce']);self.assertTrue(pending['param_hash'])
        self.assertNotIn('NEVER_PUBLIC',str(response.result));self.assertNotIn('approval_token',str(response.result))
        executor.client.send_command.assert_not_called()
        task=dispatcher.coordinator.get_task(pending['session_id'],pending['task_id'])
        self.assertEqual(task.status,TaskStatus.AWAITING_APPROVAL)
    def test_denied_and_expired_provider_states_are_terminal_failures(self):
        from mcp_service.execution.blender_executor import BlenderExecutor
        from mcp_service.security.approval import ApprovalManager,ApprovalDecision
        for state in ('denied','cancelled','expired'):
            manager=ApprovalManager();manager.set_provider(lambda tool,params:ApprovalDecision(False,'No decision to execute',request_id='owned-request',status=state))
            executor=BlenderExecutor(approval_manager=manager);executor.client=Mock()
            task=AgentTask(task_id='denied',required_capability='modeling.object_controls',task_type='configure_modeling_object',input_params={'name':'Owned','action':'transform','translation':[1,0,0],'expected_snapshot_id':'sha256:'+'a'*64})
            result=ModelingAgent().execute_task(task,executor)
            with self.subTest(state=state):
                self.assertEqual(result.status,TaskStatus.FAILED)
                self.assertEqual(result.verification.observed_results['transaction_status'],'NOT_APPLICABLE')
                executor.client.send_command.assert_not_called()
